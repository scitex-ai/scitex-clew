#!/usr/bin/env python3
"""Unconscious capture: files opened outside stx.io + imported project code.

Real files in a real project tree, the real session hooks
(``on_session_start`` / ``on_session_close`` — what ``@stx.session`` fires),
the real audit hook and a real PostgreSQL store. No mocks.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import uuid
import warnings
from pathlib import Path

import pytest
from scitex_clew._db._paths import project_root
import scitex_clew as clew
from scitex_clew import _capture
from scitex_clew._db import get_db
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import set_tracker

CAPTURE_LOGGER = "scitex_clew._capture"


@pytest.fixture(autouse=True)
def _one_clew_project_scope(tmp_path):
    """Session hooks and the reads in these tests share ONE clew project scope.

    clew scopes a session's records to the session's project root, so a read
    from the test process's cwd would look in another project. An explicit
    ``project_root`` block wins over both (scoping itself is tested in
    ``tests/scitex_clew/_core/test__project_root.py``).
    """
    with project_root(tmp_path.resolve()):
        yield


@pytest.fixture(autouse=True)
def _clean_state():
    previous = os.environ.pop(_capture.ENV_VAR, None)
    set_tracker(None)
    _capture._ACTIVE = None
    yield
    set_tracker(None)
    _capture._ACTIVE = None
    os.environ.pop(_capture.ENV_VAR, None)
    if previous is not None:
        os.environ[_capture.ENV_VAR] = previous


@pytest.fixture
def audit_off():
    """Opt out of the open capture for this test (real env var, restored)."""
    os.environ[_capture.ENV_VAR] = "0"
    yield
    os.environ.pop(_capture.ENV_VAR, None)


@pytest.fixture
def io_hooks():
    """clew's real io hooks registered with the real scitex-io."""
    sio = pytest.importorskip("scitex_io")
    from scitex_clew._observers import register_with_scitex_io

    if not register_with_scitex_io():
        pytest.fail("clew could not register its hooks with scitex-io")
    return sio


@pytest.fixture
def project(tmp_path):
    """A project tree: an entry script, a local helper module and data files."""
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    (root / "data" / "table.csv").write_text("a,b\n1,2\n3,4\n")
    (root / "data" / "notes.txt").write_text("hello\n")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "ext.txt").write_text("not part of the project\n")
    return root


@pytest.fixture
def helper(project):
    """A REAL imported project-local module (in sys.modules for the test)."""
    name = f"helper_capture_{uuid.uuid4().hex[:8]}"
    path = project / "scripts" / f"{name}.py"
    path.write_text("def double(x):\n    return 2 * x\n")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield path.resolve()
    sys.modules.pop(name, None)


def _start(project, **extra):
    sid = f"cap_{uuid.uuid4().hex[:12]}"
    meta = {"project_root": str(project), **extra}
    on_session_start(
        sid, script_path=str(project / "scripts" / "run.py"), metadata=meta
    )
    return sid


def _records(sid, role):
    return {
        r["file_path"]: r["hash"]
        for r in get_db().get_file_records(sid)
        if r["role"] == role
    }


def _external(sid):
    """``{path: via}`` of the run's inputs flagged as outside the project."""
    return {
        r["file_path"]: r["external"]["via"]
        for r in get_db().get_file_records(sid, role="input")
        if r["external"]
    }


@pytest.fixture
def elsewhere_included(project):
    """Opt the sibling ``elsewhere/`` dir in (tmp_path is under the temp dir,
    which the external-input policy excludes by default)."""
    from scitex_clew._capture._external import ENV_EXTERNAL_INCLUDE

    os.environ[ENV_EXTERNAL_INCLUDE] = str(project.parent / "elsewhere")
    yield
    os.environ.pop(ENV_EXTERNAL_INCLUDE, None)


def _capture_meta(sid):
    meta = get_db().get_run(sid)["metadata"]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    return meta["capture"]


class TestReadsAreInputs:
    def test_raw_open_read_under_the_root_is_an_input(self, project):
        # Arrange
        sid = _start(project)
        # Act
        with open(project / "data" / "notes.txt") as f:
            f.read()
        on_session_close()
        # Assert
        assert str((project / "data" / "notes.txt").resolve()) in _records(sid, "input")

    def test_pandas_read_csv_is_an_input(self, project):
        # Arrange
        pd = pytest.importorskip("pandas")
        sid = _start(project)
        # Act
        pd.read_csv(project / "data" / "table.csv")
        on_session_close()
        # Assert
        assert str((project / "data" / "table.csv").resolve()) in _records(sid, "input")

    def test_numpy_load_is_an_input(self, project):
        # Arrange
        np = pytest.importorskip("numpy")
        np.save(project / "data" / "arr.npy", np.arange(3))
        sid = _start(project)
        # Act
        np.load(project / "data" / "arr.npy")
        on_session_close()
        # Assert
        assert str((project / "data" / "arr.npy").resolve()) in _records(sid, "input")

    def test_input_hash_is_the_bytes_at_read_time(self, project):
        # Arrange
        data = project / "data" / "notes.txt"
        before = hash_file(data)
        sid = _start(project)
        # Act
        with open(data) as f:
            f.read()
        with open(data, "w") as f:
            f.write("overwritten later in the run\n")
        on_session_close()
        # Assert
        assert _records(sid, "input")[str(data.resolve())] == before

    def test_file_outside_the_project_root_is_an_external_input(
        self, project, elsewhere_included
    ):
        # Arrange
        ext = project.parent / "elsewhere" / "ext.txt"
        sid = _start(project)
        # Act
        with open(ext) as f:
            f.read()
        on_session_close()
        # Assert
        assert _external(sid) == {str(ext.resolve()): None}

    def test_symlink_inside_root_to_outside_file_is_an_external_input(
        self, project, elsewhere_included
    ):
        # Arrange
        link = project / "data" / "linked.txt"
        link.symlink_to(project.parent / "elsewhere" / "ext.txt")
        sid = _start(project)
        # Act
        with open(link) as f:
            f.read()
        on_session_close()
        # Assert
        assert _external(sid) == {
            str((project.parent / "elsewhere" / "ext.txt").resolve()): str(link)
        }

    def test_file_this_run_wrote_then_read_is_not_an_input(self, project):
        # Arrange
        tmp = project / "intermediate.txt"
        sid = _start(project)
        # Act
        tmp.write_text("made by this run\n")
        tmp.read_text()
        on_session_close()
        # Assert
        assert str(tmp.resolve()) not in _records(sid, "input")


class TestWritesAreOutputs:
    def test_raw_open_write_is_an_output_with_the_final_bytes(self, project):
        # Arrange
        out = project / "results.json"
        sid = _start(project)
        # Act
        out.write_text('{"v": 1}')
        out.write_text('{"v": 2}')
        on_session_close()
        # Assert
        assert _records(sid, "output") == {str(out.resolve()): hash_file(out)}

    def test_atomic_rename_records_the_destination(self, project):
        # Arrange
        tmp, final = project / ".results.tmp", project / "results.json"
        sid = _start(project)
        # Act
        tmp.write_text('{"v": 1}')
        os.replace(tmp, final)
        on_session_close()
        # Assert
        assert list(_records(sid, "output")) == [str(final.resolve())]

    def test_deleted_temp_file_is_not_an_output(self, project):
        # Arrange
        tmp = project / "scratch.tmp"
        sid = _start(project)
        # Act
        tmp.write_text("x")
        tmp.unlink()
        on_session_close()
        # Assert
        assert _records(sid, "output") == {}


class TestExclusions:
    @pytest.mark.parametrize(
        "rel",
        [
            ".git/config",
            "scripts/__pycache__/m.cpython-312.pyc",
            "scripts/run_out/RUNNING/ID/logs/stdout.log",
            "scripts/run_out/FINISHED_SUCCESS/ID/CONFIGS/CONFIG.yaml",
            "scripts/other_module.py",
            ".scitex/clew/runtime/claims.json",
            "lib/python3.12/site-packages/pkg/data.csv",
        ],
    )
    def test_bookkeeping_and_code_paths_are_out_of_scope(self, project, rel):
        # Arrange
        capture = _capture.RunCapture(None, project, entry_script=None)
        # Act
        decision = capture.classify(str(project / rel))
        # Assert
        assert decision is None

    def test_entry_script_is_not_a_captured_file(self, project):
        # Arrange
        script = project / "scripts" / "run.py"
        capture = _capture.RunCapture(None, project, entry_script=script)
        # Act
        decision = capture.classify(str(script))
        # Assert
        assert decision is None

    def test_data_file_under_the_root_is_in_scope(self, project):
        # Arrange
        capture = _capture.RunCapture(None, project, entry_script=None)
        # Act
        decision = capture.classify(str(project / "data" / "table.csv"))
        # Assert
        assert decision == str((project / "data" / "table.csv").resolve())

    def test_session_run_dir_is_excluded(self, project):
        # Arrange
        run_dir = project / "anywhere" / "run_dir"
        run_dir.mkdir(parents=True)
        (run_dir / "log.txt").write_text("log\n")
        sid = _start(project, sdir_run=str(run_dir))
        # Act
        (run_dir / "log.txt").read_text()
        on_session_close()
        # Assert
        assert _records(sid, "input") == {}


class TestNoDuplicateEdgesWithStxIo:
    def test_stx_io_load_plus_pandas_read_is_one_input_row(self, project, io_hooks):
        # Arrange
        pd = pytest.importorskip("pandas")
        sio = io_hooks
        data = project / "data" / "table.csv"
        sid = _start(project)
        # Act
        sio.load(str(data))
        pd.read_csv(data)
        on_session_close()
        # Assert
        rows = [
            r
            for r in get_db().get_file_records(sid)
            if r["file_path"] == str(data.resolve())
        ]
        assert [(r["role"], r["hash"]) for r in rows] == [("input", hash_file(data))]

    def test_stx_io_save_is_one_output_row(self, project, io_hooks):
        # Arrange
        sio = io_hooks
        out = project / "out" / "values.json"
        sid = _start(project)
        # Act
        sio.save({"v": 1}, str(out))
        on_session_close()
        # Assert
        rows = [
            r
            for r in get_db().get_file_records(sid)
            if r["file_path"] == str(out.resolve())
        ]
        assert [(r["role"], r["hash"]) for r in rows] == [("output", hash_file(out))]

    def test_stx_io_save_over_an_existing_csv_does_not_make_it_an_input(
        self, project, io_hooks
    ):
        # Arrange: the CSV saver reads its existing target to skip identical
        # writes; that read must not become an edge to the old bytes' producer.
        pd = pytest.importorskip("pandas")
        out = project / "out" / "table.csv"
        out.parent.mkdir()
        pd.DataFrame({"a": [1]}).to_csv(out, index=False)
        sid = _start(project)
        # Act
        io_hooks.save(pd.DataFrame({"a": [2]}), str(out), verbose=False)
        on_session_close()
        # Assert
        assert str(out.resolve()) not in _records(sid, "input")


class TestImportedCode:
    def test_imported_local_module_is_an_input(self, project, helper):
        # Arrange
        sid = _start(project)
        # Act
        on_session_close()
        # Assert
        assert _records(sid, "input") == {str(helper): hash_file(helper)}

    def test_code_inputs_are_listed_in_the_capture_metadata(self, project, helper):
        # Arrange
        sid = _start(project)
        # Act
        on_session_close()
        # Assert
        assert _capture_meta(sid)["code_inputs"] == [str(helper)]

    def test_module_imported_during_the_run_is_recorded_at_close(self, project):
        # Arrange
        sid = _start(project)
        name = f"late_{uuid.uuid4().hex[:8]}"
        path = project / "scripts" / f"{name}.py"
        path.write_text("X = 1\n")
        spec = importlib.util.spec_from_file_location(name, path)
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
        try:
            # Act
            on_session_close()
        finally:
            sys.modules.pop(name, None)
        # Assert
        assert str(path.resolve()) in _records(sid, "input")

    def test_module_changed_during_the_run_is_flagged_loudly(
        self, project, helper, caplog
    ):
        # Arrange
        sid = _start(project)
        helper.write_text("def double(x):\n    return 3 * x\n")
        # Act
        with caplog.at_level(logging.WARNING, logger=CAPTURE_LOGGER):
            on_session_close()
        # Assert
        assert (
            _capture_meta(sid)["code_changed"],
            "changed on disk" in caplog.text,
        ) == (
            [str(helper)],
            True,
        )


class TestSliceSufficiency:
    def test_claim_slice_contains_the_data_and_the_helper_module(self, project, helper):
        # Arrange
        pd = pytest.importorskip("pandas")
        out = project / "results.json"
        sid = _start(project)
        df = pd.read_csv(project / "data" / "table.csv")
        with open(project / "data" / "notes.txt") as f:
            f.read()
        out.write_text(json.dumps({"n": len(df)}))
        on_session_close()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            claim = clew.add_claim(
                str(project / "paper.tex"), "value", 1, "2", source_file=str(out)
            )
        # Act
        sl = clew.slice(claim.claim_id, level=1)
        # Assert
        assert sl.run_inputs[sid] == sorted(
            [
                str(helper),
                str((project / "data" / "table.csv").resolve()),
                str((project / "data" / "notes.txt").resolve()),
            ]
        )


class TestOptOutAndLoudness:
    def test_opt_out_env_disables_open_capture(self, project, audit_off):
        # Arrange
        sid = _start(project)
        # Act
        (project / "data" / "notes.txt").read_text()
        on_session_close()
        # Assert
        assert _records(sid, "input") == {}

    def test_opt_out_is_visible_in_metadata_and_log(self, project, audit_off, caplog):
        # Arrange
        # Act
        with caplog.at_level(logging.WARNING, logger=CAPTURE_LOGGER):
            sid = _start(project)
        on_session_close()
        # Assert
        assert (
            _capture_meta(sid)["audit"].startswith("disabled"),
            _capture.ENV_VAR in caplog.text,
        ) == (
            True,
            True,
        )

    def test_opt_out_keeps_code_capture(self, project, helper, audit_off):
        # Arrange
        # Act
        sid = _start(project)
        on_session_close()
        # Assert
        assert str(helper) in _records(sid, "input")

    def test_no_capture_between_sessions(self, project):
        # Arrange
        sid = _start(project)
        on_session_close()
        # Act
        (project / "data" / "notes.txt").read_text()
        # Assert
        assert (_capture.active_capture(), _records(sid, "input")) == (None, {})

    def test_unavailable_audit_hook_warns_and_marks_the_run(self, tmp_path):
        # Arrange: a REAL interpreter whose existing audit hook vetoes new
        # hooks (what a restricted/sandboxed interpreter does).
        child = tmp_path / "restricted.py"
        child.write_text(
            "import sys\n"
            "def veto(event, args):\n"
            "    if event == 'sys.addaudithook':\n"
            "        raise RuntimeError('audit hooks are locked')\n"
            "sys.addaudithook(veto)\n"
            "from scitex_clew import _capture\n"
            "print('STATE=' + str(_capture._install_hook()))\n"
        )
        # Act
        out = subprocess.run(
            [sys.executable, str(child)], capture_output=True, text=True, check=True
        )
        # Assert
        assert (
            "STATE=RuntimeError: sys.addaudithook was refused" in out.stdout,
            "could not install the file-access audit hook" in out.stdout + out.stderr,
        ) == (True, True)
