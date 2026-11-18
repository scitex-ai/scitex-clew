#!/usr/bin/env python3
"""The per-pass read cache of ``verify`` (``scitex_clew._chain._pass_cache``).

Real recorded runs in a real PostgreSQL store. ``CountingDB`` is a real
``VerificationDB`` subclass that counts the store reads it performs — the
reads still hit the database. No mocks.
"""

from __future__ import annotations

from collections import Counter

import pytest
from scitex_clew._chain import verify_chain
from scitex_clew._chain._pass_cache import PassRecords, pass_records
from scitex_clew._db import get_db
from scitex_clew._db._core import VerificationDB
from scitex_clew._db._paths import project_root
from scitex_clew._tracker import SessionTracker


class CountingDB(VerificationDB):
    """A real store that counts per-session and per-run reads."""

    def __init__(self) -> None:
        super().__init__()
        self.reads: Counter = Counter()

    def session_file_records(self, session_id):
        self.reads[("files", session_id)] += 1
        return super().session_file_records(session_id)

    def get_run(self, session_id):
        self.reads[("run", session_id)] += 1
        return super().get_run(session_id)


@pytest.fixture
def chain(tmp_path):
    """Three runs: raw -> step1 -> mid -> step2 -> out (each 4 extra inputs)."""
    with project_root(tmp_path.resolve()):
        raws = []
        for i in range(4):
            raw = tmp_path / f"raw{i}.txt"
            raw.write_text(f"raw {i}\n")
            raws.append(raw)
        mid, out = tmp_path / "mid.txt", tmp_path / "out.txt"
        first = SessionTracker("pc_step1", script_path=None)
        for raw in raws:
            first.record_input(raw)
        mid.write_text("mid\n")
        first.record_output(mid)
        first.finalize()
        second = SessionTracker("pc_step2", script_path=None)
        second.record_input(mid)
        second.record_input(raws[0])
        out.write_text("out\n")
        second.record_output(out)
        second.finalize()
        yield out


class TestViewsMatchTheStore:
    @pytest.mark.parametrize(
        "view",
        [
            "get_file_hashes",
            "get_frozen_files",
            "get_file_records",
            "get_external_files",
        ],
    )
    def test_cached_view_equals_uncached_view(self, chain, view):
        # Arrange
        db = get_db()
        cached = PassRecords(db)
        # Act
        got = getattr(cached, view)("pc_step1")
        # Assert
        assert got == getattr(db, view)("pc_step1")

    def test_cached_producers_equal_uncached(self, chain):
        # Arrange
        db = get_db()
        cached = PassRecords(db)
        paths = [str(chain), str(chain.parent / "mid.txt"), "/nope"]
        # Act
        got = cached.find_producer_records(paths)
        # Assert
        assert got == db.find_producer_records(paths)


class TestOneReadPerRun:
    def test_verify_reads_each_session_once(self, chain):
        # Arrange
        with project_root(chain.parent.resolve()):
            db = CountingDB()
            # Act
            result = verify_chain(chain, minimal=True, db_factory=lambda: db)
        # Assert
        assert (result.is_verified, max(db.reads.values())) == (True, 1)

    def test_wrapping_is_idempotent(self, chain):
        # Arrange
        wrapped = pass_records(get_db())
        # Act
        again = pass_records(wrapped)
        # Assert
        assert again is wrapped


# EOF
