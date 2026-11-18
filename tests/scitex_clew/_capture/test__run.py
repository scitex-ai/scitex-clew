#!/usr/bin/env python3
"""``RunCapture.hash_at_open``: a file stx.io loads is hashed ONCE.

The real audit hook (``open()``), the real session hooks and a real
PostgreSQL store. No mocks.
"""

from __future__ import annotations

import os
import uuid

import pytest
from scitex_clew import _capture
from scitex_clew._db import get_db
from scitex_clew._db._paths import project_root
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker


@pytest.fixture(autouse=True)
def _state(tmp_path):
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
def session(tmp_path):
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    data = root / "data.txt"
    data.write_text("first bytes\n")
    sid = f"hao_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(root / "scripts" / "run.py"),
        metadata={"project_root": str(root)},
    )
    yield sid, str(data.resolve())
    if get_tracker() is not None:
        on_session_close(status="success", exit_code=0)


def _open_read(path: str) -> None:
    with open(path) as handle:
        handle.read()


class TestHashAtOpen:
    def test_open_hash_is_reused_for_unchanged_bytes(self, session):
        # Arrange
        _sid, path = session
        _open_read(path)
        # Act
        reused = _capture.active_capture().hash_at_open(path)
        # Assert
        assert reused == hash_file(path)

    def test_changed_bytes_are_never_reused(self, session):
        # Arrange
        _sid, path = session
        _open_read(path)
        with open(path, "a") as handle:
            handle.write("appended later\n")
        # Act
        reused = _capture.active_capture().hash_at_open(path)
        # Assert
        assert reused is None

    def test_a_file_never_opened_has_no_open_hash(self, session):
        # Arrange
        _sid, path = session
        # Act
        reused = _capture.active_capture().hash_at_open(path + ".other")
        # Assert
        assert reused is None

    def test_recorded_input_is_the_current_bytes_after_a_change(self, session):
        # Arrange
        sid, path = session
        _open_read(path)
        with open(path, "a") as handle:
            handle.write("appended later\n")
        # Act
        get_tracker().record_input(path)
        on_session_close(status="success", exit_code=0)
        # Assert
        assert get_db().get_file_hashes(sid, role="input")[path] == hash_file(path)


# EOF
