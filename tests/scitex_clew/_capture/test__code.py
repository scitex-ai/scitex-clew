#!/usr/bin/env python3
"""Project code EXECUTED from a file (not imported) is a code input.

Each loading style researchers use — ``runpy.run_path``, ``exec(compile(...))``,
``exec(open(p).read())``, ``spec_from_file_location`` + ``exec_module`` and
IPython ``%run`` — is exercised for real inside a real session (the real
session hooks, the real audit hook, a real PostgreSQL store). No mocks.
"""

from __future__ import annotations

import importlib.util
import json
import os
import runpy
import uuid
from pathlib import Path

import pytest
import scitex_clew as clew
from scitex_clew import _capture
from scitex_clew._capture import _external
from scitex_clew._capture._code import source_digest
from scitex_clew._db import get_db
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import set_tracker

_ENVS = (_capture.ENV_VAR, _external.ENV_EXTERNAL_INCLUDE)


@pytest.fixture(autouse=True)
def _clean_state():
    saved = {k: os.environ.pop(k, None) for k in _ENVS}
    set_tracker(None)
    _capture._ACTIVE = None
    yield
    set_tracker(None)
    _capture._ACTIVE = None
    for key, value in saved.items():
        os.environ.pop(key, None)
        if value is not None:
            os.environ[key] = value


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    (root / "scripts" / "helpers.py").write_text("def double(x):\n    return 2 * x\n")
    return root


@pytest.fixture
def helpers(project):
    return project / "scripts" / "helpers.py"


def _start(project):
    sid = f"exec_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(project / "scripts" / "run.py"),
        metadata={"project_root": str(project)},
    )
    return sid


def _inputs(sid):
    return {
        r["file_path"]: r
        for r in get_db().get_file_records(sid)
        if r["role"] == "input"
    }


def _capture_meta(sid):
    meta = get_db().get_run(sid)["metadata"]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    return meta["capture"]


class TestLoadingStylesAreCodeInputs:
    def test_runpy_run_path(self, project, helpers):
        # Arrange
        sid = _start(project)
        # Act
        runpy.run_path(str(helpers))
        on_session_close()
        # Assert
        assert _inputs(sid)[str(helpers.resolve())]["hash"] == hash_file(helpers)

    def test_exec_compile_with_filename(self, project, helpers):
        # Arrange
        sid = _start(project)
        # Act
        with open(helpers) as f:
            exec(compile(f.read(), str(helpers), "exec"), {})
        on_session_close()
        # Assert
        assert str(helpers.resolve()) in _inputs(sid)

    def test_exec_of_file_text(self, project, helpers):
        # Arrange
        sid = _start(project)
        # Act
        exec(open(helpers).read(), {})
        on_session_close()
        # Assert
        assert str(helpers.resolve()) in _inputs(sid)

    def test_exec_of_file_text_with_crlf_newlines(self, project):
        # Arrange
        script = project / "scripts" / "crlf.py"
        script.write_bytes(b"A = 1\r\nB = A + 1\r\n")
        sid = _start(project)
        # Act
        exec(open(script).read(), {})
        on_session_close()
        # Assert
        assert str(script.resolve()) in _inputs(sid)

    def test_spec_from_file_location_exec_module_without_sys_modules(
        self, project, helpers
    ):
        # Arrange
        sid = _start(project)
        spec = importlib.util.spec_from_file_location("helpers_x", helpers)
        module = importlib.util.module_from_spec(spec)
        # Act
        spec.loader.exec_module(module)
        on_session_close()
        # Assert
        assert str(helpers.resolve()) in _inputs(sid)

    def test_ipython_percent_run(self, project, helpers):
        # Arrange
        interactive = pytest.importorskip("IPython.core.interactiveshell")
        shell = interactive.InteractiveShell.instance()
        sid = _start(project)
        # Act
        shell.run_line_magic("run", str(helpers))
        on_session_close()
        # Assert
        assert str(helpers.resolve()) in _inputs(sid)

    def test_exec_code_is_listed_in_the_capture_metadata(self, project, helpers):
        # Arrange
        sid = _start(project)
        # Act
        runpy.run_path(str(helpers))
        on_session_close()
        # Assert
        assert _capture_meta(sid)["exec_code_inputs"] == [str(helpers.resolve())]

    def test_claim_slice_contains_the_executed_code(self, project, helpers):
        # Arrange
        out = project / "result.json"
        sid = _start(project)
        ns = runpy.run_path(str(helpers))
        out.write_text(json.dumps({"v": ns["double"](21)}))
        on_session_close()
        claim = clew.add_claim(
            str(project / "paper.tex"), "value", 1, "42", source_file=str(out)
        )
        # Act
        sl = clew.slice(claim.claim_id, level=1)
        # Assert
        assert str(helpers.resolve()) in sl.run_inputs[sid]


class TestScope:
    def test_executed_code_outside_the_root_is_an_external_code_input(self, project):
        # Arrange: a shared lab helper next to the project (opted in: tmp_path
        # lives under the temp dir, which the external policy excludes)
        shared = project.parent / "lab-scripts"
        shared.mkdir()
        tool = shared / "lab_tool.py"
        tool.write_text("K = 3\n")
        os.environ[_external.ENV_EXTERNAL_INCLUDE] = str(shared)
        sid = _start(project)
        # Act
        runpy.run_path(str(tool))
        on_session_close()
        # Assert
        assert _inputs(sid)[str(tool.resolve())]["external"]["via"] is None

    def test_executed_code_in_the_temp_dir_is_not_recorded_by_default(self, project):
        # Arrange
        stray = project.parent / "stray.py"
        stray.write_text("Z = 0\n")
        sid = _start(project)
        # Act
        runpy.run_path(str(stray))
        on_session_close()
        # Assert
        assert str(stray.resolve()) not in _inputs(sid)

    def test_library_code_executed_is_not_recorded(self, project):
        # Arrange: a stdlib module executed by path (runpy reads + execs it)
        library_file = Path(os.__file__).with_name("colorsys.py")
        sid = _start(project)
        # Act
        runpy.run_path(str(library_file))
        on_session_close()
        # Assert
        assert [p for p in _inputs(sid) if not p.startswith(str(project))] == []

    def test_generated_code_strings_are_not_matched_to_any_file(self, project, helpers):
        # Arrange: the run READS helpers.py but execs different text
        sid = _start(project)
        helpers.read_text()
        # Act
        exec("value = 1 + 1\n", {})
        on_session_close()
        # Assert
        assert str(helpers.resolve()) not in _inputs(sid)

    def test_entry_script_executed_is_not_a_code_input(self, project):
        # Arrange
        entry = project / "scripts" / "run.py"
        sid = _start(project)
        # Act
        runpy.run_path(str(entry))
        on_session_close()
        # Assert
        assert str(entry.resolve()) not in _inputs(sid)

    def test_audit_opt_out_disables_exec_capture(self, project, helpers):
        # Arrange
        os.environ[_capture.ENV_VAR] = "0"
        sid = _start(project)
        # Act
        runpy.run_path(str(helpers))
        on_session_close()
        # Assert
        assert str(helpers.resolve()) not in _inputs(sid)


class TestSourceDigest:
    def test_crlf_bom_and_bytes_normalise_to_the_same_digest(self):
        # Arrange
        variants = (
            "A = 1\nB = 2\n",
            b"\xef\xbb\xbfA = 1\r\nB = 2\r\n",
            "A = 1\rB = 2\r",
        )
        # Act
        digests = {source_digest(v) for v in variants}
        # Assert
        assert len(digests) == 1

    def test_ast_source_has_no_digest(self):
        # Arrange
        import ast

        tree = ast.parse("x = 1")
        # Act
        digest = source_digest(tree)
        # Assert
        assert digest is None
