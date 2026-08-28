#!/usr/bin/env python3
# Timestamp: "2026-08-28 (sqlite-migration-scitex-clew-20260828)"
# File: tests/scitex_clew/test__estimate_queries.py
"""Focused join-logic tests for scitex_clew._estimate_queries._cached_intermediate_hints.

This is the trickiest of the 5 functions migrated off raw sqlite3 in this
PR: it reimplements a real SQL self-join (file_hashes JOIN file_hashes)
plus a JOIN to runs, in Python over Store rows. These tests exercise the
exact semantics of that original SQL beyond what test__estimate.py /
test__estimate_phase2.py already cover:

  - the self-join is over `file_path`, not `session_id`
  - `ORDER BY r.started_at DESC` orders by the *producer's* run, not the
    consuming session's own run
  - `JOIN runs r ON r.session_id = fh2.session_id` is an INNER JOIN — a
    producer session with no `runs` row is excluded entirely, not merely
    left unordered
  - `fh2.session_id != fh.session_id` excludes the consuming session
    itself as its own "producer"
  - `LIMIT 5` is scoped to a single `sid` iteration in the caller's loop,
    not a global cap across every session_id passed in

All test DBs are built via the package's own DB API (add_run/finish_run/
add_file_hash) plus direct `db._runs.put()` writes to control exact
`started_at` ordering — the same pattern test__estimate.py's
`_add_completed_run` helper uses, since the public API has no way to set
a custom run timestamp. No mocks, no monkeypatch (PA-306 / STX-NM002).
PA-307: one assertion per test, shared setup lifted into helper functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from scitex_dev.store import ANY_REVISION

from scitex_clew import VerificationDB
from scitex_clew._estimate import _cached_intermediate_hints
from scitex_clew._hash import hash_file as _hf


def _make_db(tmp_path: Path) -> VerificationDB:
    return VerificationDB(tmp_path / "test_queries.db")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _run_at(db: VerificationDB, session_id: str, script_path: str, started_at: datetime) -> None:
    """Register a completed run for *session_id* with an exact started_at.

    Mirrors `_add_completed_run` in test__estimate.py / test__estimate_phase2.py:
    add_run/finish_run stamp real `datetime.now()` timestamps, then a direct
    Store partial-put overwrites `started_at` for deterministic ordering.
    """
    db.add_run(session_id, script_path, script_hash=f"hash-{session_id}")
    db.finish_run(session_id, status="success")
    db._runs.put(
        {"session_id": session_id, "started_at": _iso(started_at)},
        expected_revision=ANY_REVISION,
    )


# ---------------------------------------------------------------------------
# Self-join is over file_path, not session_id
# ---------------------------------------------------------------------------


def _hints_two_producers_same_file_path(tmp_path):
    """p1 produces shared.csv (v1); p2 later re-produces it (v2, overwriting
    the on-disk file). Consumer c1 inputs the CURRENT content (v2), which
    only matches what p2 recorded — p1's recorded hash is now stale."""
    shared = tmp_path / "shared.csv"
    db = _make_db(tmp_path)

    shared.write_text("v1")
    hash_v1 = _hf(shared)
    _run_at(db, "p1", "/produce1.py", datetime(2026, 1, 1, 10, 0, 0))
    db.add_file_hash("p1", str(shared), hash_v1, "output")

    shared.write_text("v2")
    hash_v2 = _hf(shared)
    _run_at(db, "p2", "/produce2.py", datetime(2026, 1, 1, 11, 0, 0))
    db.add_file_hash("p2", str(shared), hash_v2, "output")

    _run_at(db, "c1", "/consume.py", datetime(2026, 1, 1, 12, 0, 0))
    db.add_file_hash("c1", str(shared), hash_v2, "input")

    return _cached_intermediate_hints(db, ["c1"])


class TestSelfJoinOverFilePath:
    """The self-join key is file_path, not session_id."""

    def test_only_fresh_producer_yields_a_hint(self, tmp_path):
        # Arrange — see _hints_two_producers_same_file_path: p1 (stale) and
        # p2 (fresh) both produced the same file_path.
        # Act
        hints = _hints_two_producers_same_file_path(tmp_path)
        # Assert — exactly one hint (the stale producer is filtered by the
        # freshness gate, not by the join itself).
        assert len(hints) == 1

    def test_hint_names_the_fresh_producer(self, tmp_path):
        # Arrange — see _hints_two_producers_same_file_path.
        # Act
        hints = _hints_two_producers_same_file_path(tmp_path)
        # Assert
        assert "p2" in hints[0]

    def test_hint_does_not_name_the_stale_producer(self, tmp_path):
        # Arrange — see _hints_two_producers_same_file_path.
        # Act
        hints = _hints_two_producers_same_file_path(tmp_path)
        # Assert
        assert "p1" not in hints[0]


# ---------------------------------------------------------------------------
# fh2.session_id != sid excludes the consuming session as its own producer
# ---------------------------------------------------------------------------


class TestProducerSessionExcludesSelf:
    def test_self_produced_and_self_consumed_file_yields_no_hint(self, tmp_path):
        # Arrange — session "self1" records the SAME file_path as both its
        # own output and its own input (fh2.session_id != sid must exclude it).
        artifact = tmp_path / "self.csv"
        artifact.write_text("data")
        db = _make_db(tmp_path)
        h = _hf(artifact)
        _run_at(db, "self1", "/self.py", datetime(2026, 1, 1, 9, 0, 0))
        db.add_file_hash("self1", str(artifact), h, "output")
        db.add_file_hash("self1", str(artifact), h, "input")

        # Act
        hints = _cached_intermediate_hints(db, ["self1"])

        # Assert
        assert hints == []


# ---------------------------------------------------------------------------
# JOIN runs r ON r.session_id = fh2.session_id is an INNER JOIN
# ---------------------------------------------------------------------------


def _hints_orphan_vs_good_producer(tmp_path):
    """"orphan-producer" has a file_hashes output row but NO runs row at
    all (never went through add_run). The original SQL's INNER JOIN to
    runs must drop such a producer entirely, not merely sort it last."""
    orphan_file = tmp_path / "orphan.csv"
    orphan_file.write_text("orphan data")
    good_file = tmp_path / "good.csv"
    good_file.write_text("good data")
    db = _make_db(tmp_path)

    orphan_hash = _hf(orphan_file)
    db.add_file_hash("orphan-producer", str(orphan_file), orphan_hash, "output")
    # NOTE: no db.add_run("orphan-producer", ...) call — no runs row.

    good_hash = _hf(good_file)
    _run_at(db, "good-producer", "/good.py", datetime(2026, 1, 1, 10, 0, 0))
    db.add_file_hash("good-producer", str(good_file), good_hash, "output")

    _run_at(db, "consumer", "/consume.py", datetime(2026, 1, 1, 12, 0, 0))
    db.add_file_hash("consumer", str(orphan_file), orphan_hash, "input")
    db.add_file_hash("consumer", str(good_file), good_hash, "input")

    return _cached_intermediate_hints(db, ["consumer"])


class TestInnerJoinToRuns:
    def test_only_producer_with_a_runs_row_is_hinted(self, tmp_path):
        # Arrange — see _hints_orphan_vs_good_producer.
        # Act
        hints = _hints_orphan_vs_good_producer(tmp_path)
        # Assert
        assert len(hints) == 1

    def test_hint_names_the_producer_with_a_runs_row(self, tmp_path):
        # Arrange — see _hints_orphan_vs_good_producer.
        # Act
        hints = _hints_orphan_vs_good_producer(tmp_path)
        # Assert
        assert "good-producer" in hints[0]

    def test_hint_excludes_the_producer_without_a_runs_row(self, tmp_path):
        # Arrange — see _hints_orphan_vs_good_producer.
        # Act
        hints = _hints_orphan_vs_good_producer(tmp_path)
        # Assert
        assert "orphan-producer" not in hints[0]


# ---------------------------------------------------------------------------
# LIMIT 5 is scoped to a single sid iteration, not a global cap
# ---------------------------------------------------------------------------


def _hints_six_producers_one_consumer(tmp_path):
    """A single consumer session with 6 distinct input files, each produced
    by a distinct session with a distinct started_at. ORDER BY producer
    started_at DESC + LIMIT 5 (this query's own scope) must keep only the
    5 most-recently-started producers."""
    db = _make_db(tmp_path)
    for i in range(1, 7):  # p1..p6, p6 started most recently
        f = tmp_path / f"file{i}.csv"
        f.write_text(f"content-{i}")
        h = _hf(f)
        started = datetime(2026, 1, 1, 8, 0, 0) + timedelta(hours=i)
        _run_at(db, f"p{i}", f"/produce{i}.py", started)
        db.add_file_hash(f"p{i}", str(f), h, "output")

    _run_at(db, "consumer", "/consume.py", datetime(2026, 1, 2, 0, 0, 0))
    for i in range(1, 7):
        f = tmp_path / f"file{i}.csv"
        h = _hf(f)
        db.add_file_hash("consumer", str(f), h, "input")

    return _cached_intermediate_hints(db, ["consumer"])


class TestLimitFivePerSessionId:
    def test_limit_5_returns_exactly_five_hints(self, tmp_path):
        # Arrange — see _hints_six_producers_one_consumer.
        # Act
        hints = _hints_six_producers_one_consumer(tmp_path)
        # Assert
        assert len(hints) == 5

    def test_limit_5_excludes_the_oldest_producer(self, tmp_path):
        # Arrange — see _hints_six_producers_one_consumer.
        # Act
        hints = _hints_six_producers_one_consumer(tmp_path)
        # Assert — p1 (oldest started_at) is bumped by the per-sid LIMIT 5.
        assert "p1" not in " ".join(hints)

    def test_limit_5_includes_all_five_most_recent_producers(self, tmp_path):
        # Arrange — see _hints_six_producers_one_consumer.
        # Act
        hints = _hints_six_producers_one_consumer(tmp_path)
        # Assert
        joined = " ".join(hints)
        assert all(f"p{i}" in joined for i in range(2, 7))

    def test_limit_5_reapplies_independently_per_sid_total_hints(self, tmp_path):
        # Arrange — TWO consumer sessions, each with 6 distinct producers of
        # its own (12 producers total). If LIMIT 5 were (incorrectly) global
        # across the whole session_ids list instead of per-sid, the second
        # consumer's candidates would be starved.
        db = _make_db(tmp_path)

        def _seed(consumer_id, prefix):
            for i in range(1, 7):
                f = tmp_path / f"{prefix}{i}.csv"
                f.write_text(f"{prefix}-content-{i}")
                h = _hf(f)
                started = datetime(2026, 1, 1, 8, 0, 0) + timedelta(hours=i)
                _run_at(db, f"{prefix}p{i}", f"/{prefix}produce{i}.py", started)
                db.add_file_hash(f"{prefix}p{i}", str(f), h, "output")
            _run_at(db, consumer_id, f"/{prefix}consume.py", datetime(2026, 1, 2, 0, 0, 0))
            for i in range(1, 7):
                f = tmp_path / f"{prefix}{i}.csv"
                h = _hf(f)
                db.add_file_hash(consumer_id, str(f), h, "input")

        _seed("consumerA", "a")
        _seed("consumerB", "b")

        # Act
        hints = _cached_intermediate_hints(db, ["consumerA", "consumerB"])

        # Assert — 5 hints for A's producers + 5 for B's producers = 10 total.
        assert len(hints) == 10


# EOF
