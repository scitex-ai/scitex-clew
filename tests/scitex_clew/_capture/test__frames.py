#!/usr/bin/env python3
"""Two sessions in sequence: what the SECOND one records (pilot defect F15).

A pipeline ``01`` -> ``02`` where ``02`` imports the same project module as
``01``, reads ``01``'s script as data, and runs clew's claim verification as a
validity gate inside its own session. The real audit hook, the real session
hooks, a real PostgreSQL store, real files. No mocks.

What ``02`` must record: its own imports and the files ITS code read. What it
must NOT record: the upstream files clew re-hashes while verifying a claim --
those are clew's reads, not ``02``'s, and would chain ``02`` to ``01``'s
whole input closure.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import uuid

import pytest
from scitex_clew import _capture
from scitex_clew._capture._frames import not_a_run_read
from scitex_clew._db import get_db
from scitex_clew._db._paths import project_root
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
def project(tmp_path):
    """A two-script project with a shared helper module and raw data."""
    root = tmp_path.resolve()  # the store scope of the autouse fixture
    for sub in ("code", "scripts", "data", "results"):
        (root / sub).mkdir(parents=True)
    module = f"f15_helpers_{uuid.uuid4().hex[:8]}"
    (root / "code" / f"{module}.py").write_text(
        "def mean(xs):\n    return sum(xs) / len(xs)\n"
    )
    (root / "scripts" / "01_compute.py").write_text('"""Compute the mean."""\n')
    (root / "scripts" / "02_report.py").write_text('"""Report it."""\n')
    (root / "data" / "raw.txt").write_text("1 2 3 4\n")
    sys.path.insert(0, str(root / "code"))
    yield root, module
    sys.path.remove(str(root / "code"))
    sys.modules.pop(module, None)


def _start(root, script):
    sid = f"f15_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(root / "scripts" / script),
        metadata={"project_root": str(root)},
    )
    return sid


def _close():
    on_session_close(status="success", exit_code=0)


def _inputs(sid):
    return set(get_db().get_file_hashes(sid, role="input"))


def _run_01(root, module):
    """Step 1: import the helper, read raw data, write metrics."""
    sid = _start(root, "01_compute.py")
    helpers = importlib.import_module(module)
    with open(root / "data" / "raw.txt") as f:
        values = [float(x) for x in f.read().split()]
    with open(root / "results" / "metrics.json", "w") as f:
        json.dump({"mean": helpers.mean(values)}, f)
    _close()
    return sid


class TestSecondSession:
    def test_second_session_records_its_own_imports(self, project):
        # Arrange: 01 imported the helper; it stays in sys.modules.
        root, module = project
        _run_01(root, module)
        # Act: 02 in the same process uses the already-imported helper.
        sid = _start(root, "02_report.py")
        with open(root / "results" / "metrics.json") as f:
            json.load(f)
        _close()
        # Assert
        assert str(root / "code" / f"{module}.py") in _inputs(sid)

    def test_script_read_as_data_is_an_input(self, project):
        # Arrange
        root, module = project
        _run_01(root, module)
        # Act: 02 parses 01's source to use its docstring.
        sid = _start(root, "02_report.py")
        with open(root / "scripts" / "01_compute.py") as f:
            ast.get_docstring(ast.parse(f.read()))
        _close()
        # Assert
        assert str(root / "scripts" / "01_compute.py") in _inputs(sid)

    def test_in_session_verification_adds_no_upstream_input(self, verified_02):
        # Arrange
        root, sid = verified_02
        # Act
        inputs = _inputs(sid)
        # Assert: 01's raw data is 01's input, never 02's.
        assert str(root / "data" / "raw.txt") not in inputs

    def test_in_session_verification_keeps_the_real_input(self, verified_02):
        # Arrange
        root, sid = verified_02
        # Act
        inputs = _inputs(sid)
        # Assert: the file 02's own code read stays recorded.
        assert str(root / "results" / "metrics.json") in inputs

    def test_read_back_of_own_output_is_not_an_input(self, read_back):
        # Arrange
        scratch, sid = read_back
        # Act
        inputs = _inputs(sid)
        # Assert: an intermediate, no self-edge.
        assert str(scratch) not in inputs

    def test_read_back_file_is_an_output(self, read_back):
        # Arrange
        scratch, sid = read_back
        # Act
        outputs = get_db().get_file_hashes(sid, role="output")
        # Assert
        assert str(scratch) in outputs


@pytest.fixture
def verified_02(project):
    """01 runs; 02 reads its metrics and verifies a claim inside its session."""
    import scitex_clew as clew

    root, module = project
    _run_01(root, module)
    metrics = root / "results" / "metrics.json"
    answers = root / "answers.json"
    sid = _start(root, "02_report.py")
    with open(metrics) as f:
        value = json.load(f)["mean"]
    with open(answers, "w") as f:
        json.dump({"q1": value}, f)
    clew.add_claim(
        file_path=str(answers),
        claim_type="value",
        line_number=1,
        claim_value=f"q1 = {value!r}",
        value=value,
        source_file=str(metrics),
        source_keys={".": {"pointer": "/mean"}},
        claim_id=f"q1_{sid}",
        project_root=str(root),
    )
    clew.verify_claim(f"q1_{sid}")
    clew.verify_all_claims(strict=True)
    _close()
    yield root, sid


@pytest.fixture
def read_back(project):
    """A session writes a file and reads it back."""
    root, _module = project
    scratch = root / "results" / "scratch.txt"
    sid = _start(root, "02_report.py")
    scratch.write_text("x")
    scratch.read_text()
    _close()
    yield scratch, sid


class TestNotARunRead:
    def test_user_code_open_is_a_run_read(self):
        # Arrange: called from test code, no clew frame above.
        depth = 1
        # Act
        reason = not_a_run_read(depth=depth)
        # Assert
        assert reason is None

    def test_clew_frame_on_the_stack_is_not_a_run_read(self):
        # Arrange: run the check from inside a clew (non-capture) module's frame.
        from scitex_clew import _hash

        namespace = {"__name__": _hash.__name__, "check": not_a_run_read}
        # Act
        exec("reason = check(depth=1)", namespace)
        # Assert
        assert namespace["reason"] == "clew"

    def test_capture_frames_alone_do_not_count_as_clew(self):
        # Arrange
        namespace = {"__name__": _capture.__name__, "check": not_a_run_read}
        # Act
        exec("reason = check(depth=1)", namespace)
        # Assert
        assert namespace["reason"] is None
