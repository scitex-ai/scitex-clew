#!/usr/bin/env python3
"""Package provenance stored once per environment (:mod:`scitex_clew._db._environments`).

Real PostgreSQL store (own schema per test, ``tests/conftest.py``), no mocks.
The provenance sets are the shape scitex-session records; where the session
collector is installed, a test also records the REAL collector's view of this
interpreter's distributions.
"""

from __future__ import annotations

import hashlib
import json
import os
from importlib.metadata import distributions

import pytest
from scitex_clew import VerificationDB
from scitex_clew._chain._slice_records import run_environment
from scitex_clew._db._environments import (
    REF_KEY,
    UNRESOLVED_KEY,
    canonical_provenance_bytes,
)
from scitex_dev.store import ANY_REVISION


def _provenance(n: int = 40, tag: str = "a") -> dict:
    return {
        f"dist{i:03d}": {
            "version": f"1.{i}.0",
            "source": "index",
            "fingerprint": hashlib.sha256(f"{tag}{i}".encode()).hexdigest(),
            "modified_files": [],
            "direct_url": None,
        }
        for i in range(n)
    }


def _meta(provenance: dict, **extra) -> dict:
    return {"packages": {k: v["version"] for k, v in provenance.items()},
            "package_provenance": provenance, **extra}  # fmt: skip


def _raw_meta(db: VerificationDB, sid: str) -> dict:
    return json.loads(db._runs.get((sid,)).values["metadata"])


def _env_rows(db: VerificationDB) -> list:
    return db._environments.rows()


def _sql(query: str, *params) -> list:
    """Run ``query`` on this test's own schema (the store clew writes to)."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(os.environ["SCITEX_STORE_DSN"], autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def db():
    return VerificationDB()


class TestWrite:
    def test_run_row_holds_a_reference_not_the_set(self, db):
        # Arrange
        prov = _provenance()
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        raw = _raw_meta(db, "s1")
        # Assert
        assert ("package_provenance" in raw, raw[REF_KEY]["distributions"]) == (
            False,
            40,
        )

    def test_reference_is_the_sha256_of_the_canonical_json(self, db):
        # Arrange
        prov = _provenance()
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Assert
        assert (
            _raw_meta(db, "s1")[REF_KEY]["sha256"]
            == hashlib.sha256(canonical_provenance_bytes(prov)).hexdigest()
        )

    def test_same_environment_is_stored_once(self, db):
        # Arrange
        prov = _provenance()
        # Act
        for i in range(5):
            db.add_run(f"s{i}", "/p/script.py", metadata=_meta(prov))
        # Assert
        assert len(_env_rows(db)) == 1

    def test_same_environment_from_a_fresh_process_is_not_rewritten(self, db):
        # Arrange: a second VerificationDB has an empty in-process cache
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        other = VerificationDB()
        # Act
        other.add_run("s2", "/p/script.py", metadata=_meta(prov))
        # Assert: one row, written once (one oplog entry)
        oplog = _sql("SELECT count(*) FROM environments_oplog")[0][0]
        assert (len(_env_rows(other)), oplog) == (1, 1)

    def test_distinct_environments_get_distinct_rows(self, db):
        # Arrange
        a, b = _provenance(tag="a"), _provenance(tag="b")
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(a))
        db.add_run("s2", "/p/script.py", metadata=_meta(b))
        # Assert
        assert len(_env_rows(db)) == 2

    def test_run_row_is_small_whatever_the_environment_size(self, db):
        # Arrange
        prov = _provenance(n=400)
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        stored = db._runs.get(("s1",)).values["metadata"]
        # Assert: the packages map stays; the ~200 KB provenance does not
        assert len(stored) < len(json.dumps(prov)) / 5

    def test_metadata_without_provenance_is_stored_as_given(self, db):
        # Arrange
        meta = {"sdir_out": "/x"}
        # Act
        db.add_run("s1", "/p/script.py", metadata=meta)
        # Assert
        assert (_raw_meta(db, "s1"), _env_rows(db)) == ({"sdir_out": "/x"}, [])


class TestRead:
    def test_get_run_resolves_the_provenance(self, db):
        # Arrange
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Act
        meta = json.loads(db.get_run("s1")["metadata"])
        # Assert
        assert meta["package_provenance"] == prov

    def test_a_fresh_process_resolves_from_the_store(self, db):
        # Arrange
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Act
        meta = json.loads(VerificationDB().get_run("s1")["metadata"])
        # Assert
        assert meta["package_provenance"] == prov

    def test_list_runs_resolves_the_provenance(self, db):
        # Arrange
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Act
        (run,) = db.list_runs()
        # Assert
        assert json.loads(run["metadata"])["package_provenance"] == prov

    def test_run_environment_sees_the_provenance(self, db):
        # Arrange
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Act
        env = run_environment(db, "s1")
        # Assert
        assert env["package_provenance"] == prov

    def test_a_row_written_inline_before_the_change_reads_unchanged(self, db):
        # Arrange: a pre-0.32 row — provenance inline in runs.metadata
        prov = _provenance()
        legacy = json.dumps(_meta(prov))
        db._runs.put(
            {"session_id": "old", "script_path": "/p/s.py", "metadata": legacy},
            expected_revision=ANY_REVISION,
        )
        # Act
        got = db.get_run("old")["metadata"]
        # Assert
        assert (got, run_environment(db, "old")["package_provenance"]) == (legacy, prov)

    def test_merge_keeps_the_reference_and_the_provenance(self, db):
        # Arrange
        prov = _provenance()
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Act
        db.merge_run_metadata("s1", {"capture": {"n": 1}})
        raw = _raw_meta(db, "s1")
        resolved = json.loads(db.get_run("s1")["metadata"])
        # Assert
        assert (
            "package_provenance" in raw,
            raw["capture"],
            resolved["package_provenance"],
        ) == (
            False,
            {"n": 1},
            prov,
        )

    def test_merge_into_a_legacy_inline_row_externalizes_it(self, db):
        # Arrange
        prov = _provenance()
        db._runs.put(
            {
                "session_id": "old",
                "script_path": "/p/s.py",
                "metadata": json.dumps(_meta(prov)),
            },
            expected_revision=ANY_REVISION,
        )
        # Act
        db.merge_run_metadata("old", {"capture": {"n": 1}})
        # Assert
        assert (
            REF_KEY in _raw_meta(db, "old"),
            run_environment(db, "old")["package_provenance"],
        ) == (
            True,
            prov,
        )


class TestUnresolvable:
    def _ref_only(self, db, digest: str) -> None:
        meta = {
            "packages": {"x": "1"},
            REF_KEY: {"format": "f", "sha256": digest, "distributions": 1},
        }
        db._runs.put(
            {"session_id": "r", "script_path": "/p/s.py", "metadata": json.dumps(meta)},
            expected_revision=ANY_REVISION,
        )

    def test_missing_environment_reads_as_not_recorded(self, db):
        # Arrange
        self._ref_only(db, "0" * 64)
        # Act
        env = run_environment(db, "r")
        # Assert: never "all fine" — the provenance is absent, not empty
        assert env["package_provenance"] is None

    def test_missing_environment_is_named_on_the_row(self, db):
        # Arrange
        self._ref_only(db, "0" * 64)
        # Act
        meta = json.loads(db.get_run("r")["metadata"])
        # Assert
        assert "no environment row" in meta[UNRESOLVED_KEY]

    def test_tampered_environment_row_is_not_used(self, db):
        # Arrange: the row's content no longer matches its key
        db.add_run("s1", "/p/script.py", metadata=_meta(_provenance()))
        _sql("UPDATE environments_rows SET provenance = %s", json.dumps({"x": {}}))
        # Act
        fresh = VerificationDB()
        env = run_environment(fresh, "s1")
        meta = json.loads(fresh.get_run("s1")["metadata"])
        # Assert
        assert (
            env["package_provenance"],
            "does not match" in meta[UNRESOLVED_KEY],
        ) == (None, True)

    def test_the_read_annotation_is_never_written_back(self, db):
        # Arrange
        self._ref_only(db, "0" * 64)
        # Act
        db.merge_run_metadata("r", {"capture": {"n": 1}})
        # Assert
        assert UNRESOLVED_KEY not in _raw_meta(db, "r")


class TestSessionConformance:
    def test_real_collector_record_round_trips(self, db):
        # Arrange: the session collector's view of real installed distributions
        dp = pytest.importorskip("scitex_session._lifecycle._dist_provenance")
        dists = [d for d in distributions() if d.read_text("RECORD")][:30]
        prov = {d.metadata["Name"]: dp.distribution_provenance(d) for d in dists}
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        got = run_environment(VerificationDB(), "s1")["package_provenance"]
        # Assert
        assert got == json.loads(json.dumps(prov, default=str))

    def test_hash_matches_the_session_environment_file_name(self, db):
        # Arrange
        es = pytest.importorskip("scitex_session._lifecycle._env_store")
        prov = _provenance()
        # Act
        db.add_run("s1", "/p/script.py", metadata=_meta(prov))
        # Assert
        assert (
            _raw_meta(db, "s1")[REF_KEY]["sha256"]
            == hashlib.sha256(es.canonical_provenance_bytes(prov)).hexdigest()
        )


# EOF
