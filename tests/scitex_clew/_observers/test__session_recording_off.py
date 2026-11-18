#!/usr/bin/env python3
"""``SCITEX_CLEW_CAPTURE=0`` — the whole-capture off switch.

The real session hooks, the real scitex-io hooks and a real PostgreSQL store;
the switch is the real environment variable. No mocks.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid

import pytest
from scitex_clew import _capture
from scitex_clew._db import get_db
from scitex_clew._db._paths import project_root
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker


@pytest.fixture(autouse=True)
def _state(tmp_path):
    previous = os.environ.pop(_capture.CAPTURE_ENV_VAR, None)
    set_tracker(None)
    _capture._ACTIVE = None
    with project_root(tmp_path.resolve()):
        yield
    set_tracker(None)
    _capture._ACTIVE = None
    os.environ.pop(_capture.CAPTURE_ENV_VAR, None)
    if previous is not None:
        os.environ[_capture.CAPTURE_ENV_VAR] = previous


@pytest.fixture
def recording_off():
    os.environ[_capture.CAPTURE_ENV_VAR] = "0"
    yield


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
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    (root / "data.csv").write_text("x\n1\n")
    return root


def _run(project, sio) -> str:
    sid = f"off_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(project / "scripts" / "run.py"),
        metadata={"project_root": str(project)},
    )
    sio.save(
        sio.load(str(project / "data.csv")), str(project / "out.csv"), verbose=False
    )
    on_session_close(status="success", exit_code=0)
    return sid


class TestSwitchValues:
    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF"])
    def test_falsy_values_turn_recording_off(self, value):
        # Arrange
        os.environ[_capture.CAPTURE_ENV_VAR] = value
        # Act
        enabled = _capture.recording_enabled()
        # Assert
        assert enabled is False

    @pytest.mark.parametrize("value", ["1", "true", "on"])
    def test_truthy_values_keep_recording_on(self, value):
        # Arrange
        os.environ[_capture.CAPTURE_ENV_VAR] = value
        # Act
        enabled = _capture.recording_enabled()
        # Assert
        assert enabled is True

    def test_unset_switch_keeps_recording_on(self):
        # Arrange — the autouse fixture removed the variable
        # Act
        enabled = _capture.recording_enabled()
        # Assert
        assert enabled is True


class TestRecordingOff:
    def test_no_run_is_recorded(self, project, sio, recording_off):
        # Arrange
        # Act
        sid = _run(project, sio)
        # Assert
        assert get_db().get_run(sid) is None

    def test_no_file_rows_are_recorded(self, project, sio, recording_off):
        # Arrange
        # Act
        sid = _run(project, sio)
        # Assert
        assert get_db().get_file_records(sid) == []

    def test_no_tracker_and_no_capture_are_active(self, project, recording_off):
        # Arrange
        # Act
        on_session_start("off_probe", metadata={"project_root": str(project)})
        # Assert
        assert (get_tracker(), _capture.active_capture()) == (None, None)

    def test_close_without_a_start_is_a_no_op(self, recording_off):
        # Arrange
        # Act
        result = on_session_close(status="success", exit_code=0)
        # Assert
        assert result is None

    def test_recording_on_records_the_same_run(self, project, sio):
        # Arrange
        # Act
        sid = _run(project, sio)
        # Assert
        assert len(get_db().get_file_records(sid)) == 2


class TestLoudAndStoreFree:
    def test_a_warning_says_recording_is_off(self, tmp_path):
        # Arrange
        code = (
            "import logging, scitex_clew._observers as o;"
            "logging.basicConfig(level=logging.WARNING);"
            "o.on_io_load(__import__('pathlib').Path('x'), None)"
        )
        env = {
            "HOME": os.environ.get("HOME", "/"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
            _capture.CAPTURE_ENV_VAR: "0",
            "SCITEX_STORE_DSN": "postgresql://nobody@127.0.0.1:1/never",
        }
        # Act
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
            check=False,
        )
        # Assert
        assert "provenance recording is OFF" in out.stderr

    def test_io_hook_never_connects_to_the_store(self, tmp_path):
        # Arrange — an unreachable store: any connection attempt would fail
        code = (
            "import scitex_clew._observers as o, pathlib;"
            "o.on_io_load(pathlib.Path('x'), None);"
            "o.on_io_save(pathlib.Path('x'), 1, {});"
            "import scitex_clew._db._core as c;"
            "print('opened' if c._DB_INSTANCE is not None else 'untouched')"
        )
        env = {
            "HOME": os.environ.get("HOME", "/"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
            _capture.CAPTURE_ENV_VAR: "0",
            "SCITEX_STORE_DSN": "postgresql://nobody@127.0.0.1:1/never",
        }
        # Act
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
            check=False,
        )
        # Assert
        assert out.stdout.strip() == "untouched"


def test_warning_is_logged_once_per_process(caplog, recording_off):
    # Arrange
    _capture._WARNED_OFF = False
    caplog.set_level(logging.WARNING)
    # Act
    _capture.warn_recording_off()
    _capture.warn_recording_off()
    # Assert
    assert sum("recording is OFF" in r.getMessage() for r in caplog.records) == 1


# EOF
