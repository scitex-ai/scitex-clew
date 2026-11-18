#!/usr/bin/env python3
"""Batched recording records EXACTLY what per-file recording did.

A session's file rows are queued and written in one transaction, and its
inputs' producers are bound at flush time (``scitex_clew._tracker_batch``).
These tests drive the real session hooks (what ``@stx.session`` fires), the
real scitex-io hooks, the real ``open()`` audit capture and a real PostgreSQL
store, and compare a batched run with the SAME run flushed after every file
(one commit per file, the old behaviour). No mocks.
"""

from __future__ import annotations

import os
import uuid

import pytest
from scitex_clew import _capture
from scitex_clew._chain._routes import parents_of
from scitex_clew._db import get_db
from scitex_clew._db._paths import project_root
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker

#: Row fields that must not depend on how the rows were committed.
_CONTENT = ("file_path", "role", "hash", "size_bytes", "external", "derived_from")


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    previous = os.environ.pop(_capture.ENV_VAR, None)
    set_tracker(None)
    _capture._ACTIVE = None
    with project_root(tmp_path.resolve()):
        yield
    set_tracker(None)
    _capture._ACTIVE = None
    if previous is not None:
        os.environ[_capture.ENV_VAR] = previous


@pytest.fixture
def sio():
    sio = pytest.importorskip("scitex_io")
    from scitex_clew._observers import register_with_scitex_io

    if not register_with_scitex_io():
        pytest.fail("clew could not register its hooks with scitex-io")
    return sio


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    for name in ("a", "b", "c"):
        (root / "data" / f"{name}.csv").write_text(f"x\n{name}\n")
    return root


def _session(project, body) -> str:
    sid = f"batch_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(project / "scripts" / "run.py"),
        metadata={"project_root": str(project)},
    )
    body()
    on_session_close(status="success", exit_code=0)
    return sid


def _run_pair(project, sio, *, flush_each: bool) -> tuple[str, str]:
    """A producer run, then a consumer of its output; returns both ids."""
    data = project / "data"
    mid = project / "results" / "mid.csv"
    out = project / "results" / f"out_{int(flush_each)}.csv"

    def step():
        if flush_each:
            get_tracker().flush_pending()

    def produce():
        sio.load(str(data / "a.csv"))
        step()
        sio.save(sio.load(str(data / "b.csv")), str(mid), verbose=False)
        step()

    def consume():
        frame = sio.load(str(mid))
        step()
        with open(data / "c.csv") as handle:  # a plain open(): audit capture
            handle.read()
        step()
        sio.save(frame, str(out), verbose=False)
        step()

    return _session(project, produce), _session(project, consume)


def _content(sid: str) -> list[tuple]:
    """The run's rows minus what legitimately differs (ids, record times)."""
    rows = get_db().get_file_records(sid)
    out = []
    for r in rows:
        path = r["file_path"]
        if path.endswith(("out_0.csv", "out_1.csv")):
            path = path[: -len("_0.csv")] + "_N.csv"
        values = {**r, "file_path": path}
        # repr: makes None / dict values orderable for the sort below
        out.append((path, r["role"], *(repr(values[k]) for k in _CONTENT[2:])))
    return sorted(out)


class TestBatchedEqualsPerFile:
    def test_producer_rows_are_identical(self, project, sio):
        # Arrange
        batched, _ = _run_pair(project, sio, flush_each=False)
        # Act
        per_file, _ = _run_pair(project, sio, flush_each=True)
        # Assert
        assert _content(batched) == _content(per_file)

    def test_consumer_rows_are_identical(self, project, sio):
        # Arrange
        _, batched = _run_pair(project, sio, flush_each=False)
        # Act
        _, per_file = _run_pair(project, sio, flush_each=True)
        # Assert
        assert _content(batched) == _content(per_file)

    def test_consumer_rows_are_the_files_it_read_and_wrote(self, project, sio):
        # Arrange
        root = project.resolve()
        expected = sorted(
            [
                (str(root / "results" / "mid.csv"), "input"),
                (str(root / "data" / "c.csv"), "input"),
                (str(root / "results" / "out_N.csv"), "output"),
            ]
        )
        # Act
        _, consumer = _run_pair(project, sio, flush_each=False)
        # Assert
        assert sorted(row[:2] for row in _content(consumer)) == expected

    def test_recorded_hashes_are_the_bytes_on_disk(self, project, sio):
        # Arrange
        _, consumer = _run_pair(project, sio, flush_each=False)
        # Act
        recorded = get_db().get_file_hashes(consumer)
        # Assert
        assert recorded == {p: hash_file(p) for p in recorded}

    def test_consumer_is_bound_to_its_producer(self, project, sio):
        # Arrange
        producer, consumer = _run_pair(project, sio, flush_each=False)
        # Act
        parents = parents_of(get_db(), consumer)
        # Assert
        assert parents == [producer]

    def test_legacy_parent_junction_matches_per_file_binding(self, project, sio):
        # Arrange
        p_batched, c_batched = _run_pair(project, sio, flush_each=False)
        p_each, c_each = _run_pair(project, sio, flush_each=True)
        # Act
        got = (get_db().get_parents(c_batched), get_db().get_parents(c_each))
        # Assert
        assert got == ([p_batched], [p_each])


class TestQueuedUntilClose:
    def test_rows_are_queued_not_committed_during_the_session(self, project, sio):
        # Arrange
        on_session_start(
            "batch_open_session",
            script_path=str(project / "scripts" / "run.py"),
            metadata={"project_root": str(project)},
        )
        # Act
        sio.load(str(project / "data" / "a.csv"))
        pending = get_db()._file_hashes.pending
        on_session_close(status="success", exit_code=0)
        # Assert
        assert pending == 1

    def test_parent_session_reads_through_the_queue(self, project, sio):
        # Arrange
        producer, _ = _run_pair(project, sio, flush_each=False)
        on_session_start(
            "batch_parent_read",
            script_path=str(project / "scripts" / "run.py"),
            metadata={"project_root": str(project)},
        )
        sio.load(str(project / "results" / "mid.csv"))
        # Act
        parent = get_tracker().parent_session
        on_session_close(status="success", exit_code=0)
        # Assert
        assert parent == producer


# EOF
