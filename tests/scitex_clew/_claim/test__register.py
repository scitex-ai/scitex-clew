#!/usr/bin/env python3
"""Tests for the add_claim dedup fix (:mod:`scitex_clew._claim._register`).

Before the fix, ``claim_id`` was ``hash(file_path, line_number, claim_type)`` —
so two DISTINCT numbers on the same line collapsed under INSERT OR REPLACE,
silently dropping claims (biting the "register everything" workflow at scale).
The fix folds ``claim_value`` into the id and adds an explicit ``claim_id``
override.

Per PA-306 §3 (no mocks): real isolated DB. Per PA-307 §3: AAA markers + one
assertion per test.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import pytest
import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._tracker import SessionTracker


@pytest.fixture(autouse=True)
def isolated_db():
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield _db_module.get_db()
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _tex(tmp_path):
    p = tmp_path / "paper.tex"
    p.write_text("acc 0.70 and spec 0.96 on one line\n")
    return str(p)


def _unowned_source(tmp_path):
    p = tmp_path / "metrics.json"
    p.write_text('{"acc": 0.70}\n')
    return str(p)


class TestAddClaimDedup:
    def test_distinct_values_same_line_get_distinct_ids(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        # Act
        a = clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.70"
        )
        b = clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.96"
        )
        # Assert
        assert a.claim_id != b.claim_id

    def test_distinct_values_same_line_both_persist(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.70"
        )
        clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.96"
        )
        # Act
        rows = clew.list_claims(file_path=tex)
        # Assert
        assert len(rows) == 2

    def test_line_number_none_distinct_values_dont_collapse(
        self, isolated_db, tmp_path
    ):
        # Arrange
        tex = _tex(tmp_path)
        clew.add_claim(file_path=tex, claim_type="value", claim_value="0.70")
        clew.add_claim(file_path=tex, claim_type="value", claim_value="0.96")
        # Act
        rows = clew.list_claims(file_path=tex)
        # Assert
        assert len(rows) == 2

    def test_same_value_reregistration_is_idempotent(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.70"
        )
        clew.add_claim(
            file_path=tex, claim_type="value", line_number=1, claim_value="0.70"
        )
        # Act
        rows = clew.list_claims(file_path=tex)
        # Assert
        assert len(rows) == 1


class TestAddClaimExplicitId:
    def test_explicit_claim_id_used_verbatim(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        # Act
        c = clew.add_claim(
            file_path=tex,
            claim_type="figure",
            claim_value="Fig1",
            claim_id="figures/fig1.png",
        )
        # Assert
        assert c.claim_id == "figures/fig1.png"

    def test_explicit_empty_claim_id_raises_value_error(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        # Act
        # Assert
        with pytest.raises(ValueError):
            clew.add_claim(file_path=tex, claim_type="value", claim_id="   ")

    def test_explicit_id_reregistration_overwrites(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        clew.add_claim(
            file_path=tex,
            claim_type="figure",
            claim_id="figures/fig1.png",
            claim_value="v1",
        )
        clew.add_claim(
            file_path=tex,
            claim_type="figure",
            claim_id="figures/fig1.png",
            claim_value="v2",
        )
        # Act
        rows = clew.list_claims(file_path=tex)
        # Assert
        assert len(rows) == 1


class TestAddClaimNoLineageWarning:
    def test_unowned_source_file_warns_no_lineage(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        src = _unowned_source(tmp_path)
        # Act
        # Assert
        with pytest.warns(RuntimeWarning, match="NO_LINEAGE"):
            clew.add_claim(
                file_path=tex,
                claim_type="value",
                claim_value="0.70",
                source_file=src,
            )

    def test_owned_source_file_does_not_warn_no_lineage(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        src = _unowned_source(tmp_path)
        isolated_db.add_run("sess-owned", str(tmp_path / "script.py"))
        isolated_db.add_file_hash(
            "sess-owned",
            str(Path(src).resolve()),
            "deadbeef",
            role="output",
        )
        # Act
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            clew.add_claim(
                file_path=tex,
                claim_type="value",
                claim_value="0.70",
                source_file=src,
            )
        # Assert
        assert not any("NO_LINEAGE" in str(w.message) for w in caught)

    def test_env_opt_out_suppresses_no_lineage_warning(self, isolated_db, tmp_path):
        # Arrange
        tex = _tex(tmp_path)
        src = _unowned_source(tmp_path)
        prev = os.environ.get("SCITEX_CLEW_WARN_NO_LINEAGE")
        os.environ["SCITEX_CLEW_WARN_NO_LINEAGE"] = "0"
        # Act
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                clew.add_claim(
                    file_path=tex,
                    claim_type="value",
                    claim_value="0.71",
                    source_file=src,
                )
        finally:
            if prev is None:
                os.environ.pop("SCITEX_CLEW_WARN_NO_LINEAGE", None)
            else:
                os.environ["SCITEX_CLEW_WARN_NO_LINEAGE"] = prev
        # Assert
        assert not any("NO_LINEAGE" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# Native claim fields, re-add after remove, project_root=
# ---------------------------------------------------------------------------


def _produce(tmp_path, name, content, sid="S1"):
    script = tmp_path / "make.py"
    script.write_text("# make\n")
    out = tmp_path / name
    out.write_text(content)
    tracker = SessionTracker(sid, script_path=str(script))
    tracker.record_output(out)
    tracker.finalize()
    return out


def _claim(tmp_path, display, source, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return clew.add_claim(
            str(tmp_path / "paper.tex"),
            "value",
            1,
            display,
            source_file=str(source),
            **kw,
        )


@pytest.fixture
def results_json(tmp_path):
    return _produce(
        tmp_path, "results.json", json.dumps({"test": {"auc": 0.8123, "n": 120}})
    )


class TestNativeClaimFields:
    def test_fields_round_trip_and_display_string_is_kept(self, tmp_path, results_json):
        # Arrange
        _claim(
            tmp_path,
            "AUC = 0.81",
            results_json,
            value={"auc": 0.81},
            source_keys={"auc": "/test/auc"},
            tolerance={"rel_tol": 0.01},
            metadata={"writer_schema": 1, "macro": "\\clewAuc"},
        )
        # Act
        c = clew.list_claims()[0]
        # Assert
        assert (c.claim_value, c.value, c.source_keys, c.tolerance, c.metadata) == (
            "AUC = 0.81",
            {"auc": 0.81},
            {"auc": {"pointer": "/test/auc"}},
            {"rel_tol": 0.01},
            {"writer_schema": 1, "macro": "\\clewAuc"},
        )


class TestReAddAfterRemove:
    def test_readded_claim_is_visible(self, tmp_path, results_json):
        # Arrange
        _claim(tmp_path, "0.81", results_json, claim_id="auc")
        clew.remove_claim("auc")
        # Act
        _claim(tmp_path, "0.81", results_json, claim_id="auc")
        # Assert
        assert [c.claim_id for c in clew.list_claims()] == ["auc"]


class TestProjectRoot:
    def test_project_root_scopes_without_chdir(self, tmp_path):
        # Arrange
        a, b = tmp_path / "proj_a", tmp_path / "proj_b"
        for root in (a, b):
            (root / ".git").mkdir(parents=True)
            (root / "r.json").write_text("{}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim(
                "paper.tex",
                "value",
                1,
                "1",
                source_file="r.json",
                claim_id="x",
                project_root=a,
            )
        # Act
        seen = (
            [c.claim_id for c in clew.list_claims(project_root=a)],
            [c.claim_id for c in clew.list_claims(project_root=b)],
        )
        # Assert
        assert seen == (["x"], [])

    def test_relative_paths_resolve_against_project_root(self, tmp_path):
        # Arrange
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        (root / "r.json").write_text("{}")
        # Act
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            claim = clew.add_claim(
                "paper.tex", "value", 1, "1", source_file="r.json", project_root=root
            )
        # Assert
        assert claim.source_file == str((root / "r.json").resolve())

    def test_project_root_info_resolves_from_a_subdirectory(self, tmp_path):
        # Arrange: a tool working on <root>/.scitex/writer (e.g. a manuscript
        # workspace) must scope to the RESEARCH root, as a chdir there would
        root = tmp_path / "proj"
        workspace = root / ".scitex" / "writer"
        workspace.mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname = 'p'\n")
        # Act
        info = clew.project_root_info(start=workspace)
        # Assert
        assert (info["project_root"], info["project_root_source"]) == (
            str(root.resolve()),
            "marker",
        )

    def test_project_root_block_is_public_and_chdir_free(self, tmp_path):
        # Arrange
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        cwd = os.getcwd()
        # Act
        with clew.project_root(root):
            inside = clew.project_root_info()["project_root"]
        # Assert
        assert (inside, os.getcwd()) == (str(root.resolve()), cwd)


# EOF
