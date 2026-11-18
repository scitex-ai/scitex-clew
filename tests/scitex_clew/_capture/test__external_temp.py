#!/usr/bin/env python3
"""Temp-dir files: recorded when they PRE-EXIST the process, ignored when the
process tree made them (see "Temporary directories" in
:mod:`scitex_clew._capture._external`).

Real-world origin: an agent's shell command made a scratch directory and a
symlink under ``/tmp`` outside any session; sessions then read their inputs
from it. Clew used to drop every temp-dir read, so the minimal DAG looked
complete while every replay failed. These tests reproduce that shape for
real: the test (parent) process makes the temp state, then a SEPARATE Python
process — a fresh process tree, exactly like a script launched after the
shell command — runs a real clew session (real audit hook, real session
hooks) against a real PostgreSQL schema. The child gets a PRIVATE ``TMPDIR``
(created and removed here) and an explicit allowlisted environment.

No mocks: the in-process unit tests at the bottom inject only plain values
(``temp=`` roots, ``process_start=``) into the real policy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import uuid
import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

import scitex_clew as clew
from scitex_clew import _capture
from scitex_clew._capture import _external as _capture_external
from scitex_clew._capture._external import ExternalPolicy, process_start_time
from scitex_clew._chain._slice import build_slice
from scitex_clew._claim._verify import verify_all_claims, verify_claim
from scitex_clew._cli._exit_codes import EXTERNAL_MISSING
from scitex_clew._db import get_db
from scitex_clew._db._paths import project_root
from scitex_clew._hash import hash_file
from scitex_clew._tracker import set_tracker

#: The ``src`` dir of the clew under test (the child must import THIS clew).
_SRC = str(Path(clew.__file__).resolve().parents[1])

_CHILD = textwrap.dedent(
    """
    import json, os, subprocess, sys
    from scitex_clew._observers._session import on_session_close, on_session_start

    spec = json.loads(sys.argv[1])

    def act(kind, path):
        if kind == "read":
            with open(path, "rb") as f:
                f.read()
        elif kind == "write":
            with open(path, "w") as f:
                f.write("# made by this process\\n")
        elif kind == "spawn_write":
            # A CHILD of this process makes the file (process tree).
            subprocess.run(
                [sys.executable, "-c",
                 "import sys; open(sys.argv[1], 'w').write('made by a child')",
                 path],
                check=True, env={"PATH": os.environ.get("PATH", "")},
            )
        elif kind == "exec":
            with open(path) as f:
                exec(compile(f.read(), path, "exec"), {})
        elif kind == "matplotlib":
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            ax.plot([0, 1], [1, 0])
            ax.set_title("churn")
            fig.savefig(path)
            plt.close(fig)
        else:
            raise ValueError(kind)

    for kind, path in spec["before"]:
        act(kind, path)
    on_session_start(
        spec["sid"], script_path=spec["script"],
        metadata={"project_root": spec["project"]},
    )
    for kind, path in spec["during"]:
        act(kind, path)
    with open(spec["out"], "w") as f:
        f.write(json.dumps({"ok": 1}))
    on_session_close()
    """
)

_ENVS = (
    _capture.ENV_VAR,
    _capture_external.ENV_EXTERNAL,
    _capture_external.ENV_EXTERNAL_INCLUDE,
    _capture_external.ENV_EXTERNAL_EXCLUDE,
)


@pytest.fixture(autouse=True)
def _one_clew_project_scope(tmp_path):
    """Parent queries and the child's records share ONE project scope."""
    with project_root(tmp_path.resolve()):
        yield


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
    root = tmp_path.resolve() / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    (root / "data" / "local.csv").write_text("k,v\n1,2\n")
    return root


@pytest.fixture
def private_tmp(tmp_path):
    """The child's PRIVATE ``TMPDIR`` — made here, removed afterwards."""
    path = tmp_path.resolve() / "private-tmp"
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def scratch(private_tmp):
    """Hand-made temp state that exists BEFORE the child process starts."""
    path = private_tmp / "scratch"
    path.mkdir()
    (path / "raw.csv").write_text("a,b\n1,2\n3,4\n")
    return path


def _child_env(tmpdir: Path, **extra: str) -> dict[str, str]:
    """Explicit allowlist — never the parent's whole environment."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(tmpdir)),
        "LANG": "C.UTF-8",
        "TMPDIR": str(tmpdir),
        "PYTHONPATH": _SRC,
        "SCITEX_STORE_DSN": os.environ["SCITEX_STORE_DSN"],
        "SCITEX_CLEW_PROJECT": get_db()._runs.project,
    }
    for key in ("COVERAGE_PROCESS_START", "COVERAGE_FILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(extra)
    return env


def _run_child(project, tmpdir, during, before=(), **env) -> str:
    """Run ONE session in a fresh process; return its session id."""
    sid = f"tmp_{uuid.uuid4().hex[:12]}"
    child = project.parent / "child_session.py"
    child.write_text(_CHILD)
    spec = {
        "sid": sid,
        "script": str(project / "scripts" / "run.py"),
        "project": str(project),
        "out": str(project / "results.json"),
        "before": [[k, str(p)] for k, p in before],
        "during": [[k, str(p)] for k, p in during],
    }
    proc = subprocess.run(
        [sys.executable, str(child), json.dumps(spec)],
        cwd=project,
        env=_child_env(tmpdir, **env),
        capture_output=True,
        text=True,
        timeout=120,
    )
    stderr = proc.stderr.replace(os.environ["SCITEX_STORE_DSN"], "<dsn>")
    assert proc.returncode == 0, stderr[-3000:]
    return sid


def _inputs(sid):
    return {
        r["file_path"]: r
        for r in get_db().get_file_records(sid)
        if r["role"] == "input"
    }


def _external_inputs(sid):
    return sorted(p for p, r in _inputs(sid).items() if r["external"])


def _metadata(sid):
    meta = get_db().get_run(sid)["metadata"]
    return json.loads(meta) if isinstance(meta, str) else meta


def _claim_on_results(project):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return clew.add_claim(
            str(project / "paper.tex"),
            "value",
            1,
            "1",
            source_file=str(project / "results.json"),
        )


class TestPreexistingTempFilesAreInputs:
    def test_preexisting_temp_file_is_an_external_input_with_its_hash(
        self, project, private_tmp, scratch
    ):
        # Arrange
        raw = scratch / "raw.csv"
        # Act
        sid = _run_child(project, private_tmp, during=[("read", raw)])
        # Assert
        row = _inputs(sid)[str(raw)]
        assert (row["hash"], row["external"]["via"], row["external"]["size"]) == (
            hash_file(raw),
            None,
            raw.stat().st_size,
        )

    def test_capture_metadata_lists_it_and_describes_the_temp_rule(
        self, project, private_tmp, scratch
    ):
        # Arrange
        raw = scratch / "raw.csv"
        # Act
        sid = _run_child(project, private_tmp, during=[("read", raw)])
        # Assert
        capture = _metadata(sid)["capture"]
        assert (
            capture["external_inputs"],
            capture["external"]["temp"]["rule"],
            str(private_tmp) in capture["external"]["temp"]["roots"],
        ) == ([str(raw)], "pre-existing", True)

    def test_verify_reports_external_missing_when_it_is_gone(
        self, project, private_tmp, scratch
    ):
        # Arrange
        raw = scratch / "raw.csv"
        _run_child(project, private_tmp, during=[("read", raw)])
        claim = _claim_on_results(project)
        raw.unlink()
        # Act
        result = verify_all_claims()
        detail = verify_claim(claim.claim_id)
        # Assert
        assert (result.exit_code, detail["external_missing"]) == (
            EXTERNAL_MISSING,
            [str(raw)],
        )

    def test_cli_verify_of_the_run_exits_22_when_it_is_gone(
        self, project, private_tmp, scratch
    ):
        # Arrange
        from scitex_clew._cli._verification_core import verify

        raw = scratch / "raw.csv"
        sid = _run_child(project, private_tmp, during=[("read", raw)])
        raw.unlink()
        # Act
        result = CliRunner().invoke(verify, [sid])
        # Assert
        assert result.exit_code == EXTERNAL_MISSING == 22

    def test_slice_lists_it_as_required_not_bundled(
        self, project, private_tmp, scratch
    ):
        # Arrange
        raw = scratch / "raw.csv"
        sid = _run_child(project, private_tmp, during=[("read", raw)])
        # Act
        manifest = build_slice([str(project / "results.json")]).to_dict()
        # Assert
        assert [(r["path"], r["runs"]) for r in manifest["required_not_bundled"]] == [
            (str(raw), [sid])
        ]

    def test_preexisting_temp_code_executed_by_the_run_is_a_code_input(
        self, project, private_tmp, scratch
    ):
        # Arrange: a helper a shell command staged in temp, exec'd by the run
        helper = scratch / "helper.py"
        helper.write_text("VALUE = 41 + 1\n")
        # Act
        sid = _run_child(project, private_tmp, during=[("exec", helper)])
        # Assert
        assert _external_inputs(sid) == [str(helper)]


class TestProcessTreeChurnIsNotRecorded:
    def test_temp_file_the_session_writes_then_reads_is_not_an_input(
        self, project, private_tmp
    ):
        # Arrange
        made = private_tmp / "made_in_session.bin"
        # Act
        sid = _run_child(project, private_tmp, during=[("write", made), ("read", made)])
        # Assert
        assert _external_inputs(sid) == []

    def test_temp_file_made_by_this_process_before_the_session_is_not_an_input(
        self, project, private_tmp
    ):
        # Arrange: a kernel/runtime file the SAME process made earlier
        # (a notebook's earlier cell, a kernel's cell file).
        made = private_tmp / "kernel_runtime.json"
        # Act
        sid = _run_child(
            project, private_tmp, before=[("write", made)], during=[("read", made)]
        )
        # Assert
        assert _external_inputs(sid) == []

    def test_temp_file_made_by_a_child_process_is_not_an_input(
        self, project, private_tmp
    ):
        # Arrange
        made = private_tmp / "from_subprocess.txt"
        # Act
        sid = _run_child(
            project, private_tmp, during=[("spawn_write", made), ("read", made)]
        )
        # Assert
        assert _external_inputs(sid) == []

    def test_preexisting_temp_file_rewritten_by_the_process_tree_is_not_an_input(
        self, project, private_tmp, scratch
    ):
        # Arrange: it existed, but a child of the run regenerated it
        raw = scratch / "raw.csv"
        # Act
        sid = _run_child(
            project, private_tmp, during=[("spawn_write", raw), ("read", raw)]
        )
        # Assert
        assert _external_inputs(sid) == []

    def test_temp_code_made_by_this_process_is_not_a_code_input(
        self, project, private_tmp
    ):
        # Arrange: an IPython-style cell file written then exec'd in-process
        cell = private_tmp / "ipykernel_1" / "cell.py"
        cell.parent.mkdir()
        # Act
        sid = _run_child(
            project,
            private_tmp,
            during=[("write", cell), ("exec", cell)],
        )
        # Assert
        assert _external_inputs(sid) == []

    def test_matplotlib_temp_config_churn_is_not_recorded(
        self, project, private_tmp, scratch
    ):
        # Arrange: an unwritable config dir makes matplotlib fall back to a
        # fresh temp config/cache dir (its real behaviour on locked-down hosts)
        pytest.importorskip("matplotlib")
        locked = private_tmp / "locked"
        locked.mkdir(mode=0o500)
        raw = scratch / "raw.csv"
        try:
            # Act
            sid = _run_child(
                project,
                private_tmp,
                during=[("read", raw), ("matplotlib", project / "fig.png")],
                MPLCONFIGDIR=str(locked / "mpl"),
            )
        finally:
            locked.chmod(0o700)
        # Assert: exactly the hand-made input, none of the library churn
        assert _external_inputs(sid) == [str(raw)]


class TestSymlinksThroughTemp:
    def test_in_project_link_to_a_preexisting_temp_file(
        self, project, private_tmp, scratch
    ):
        # Arrange
        link = project / "data" / "raw.csv"
        link.symlink_to(scratch / "raw.csv")
        # Act
        sid = _run_child(project, private_tmp, during=[("read", link)])
        # Assert
        row = _inputs(sid)[str(scratch / "raw.csv")]
        assert (row["external"]["via"], _metadata(sid)["capture"]["links"]) == (
            str(link),
            [str(link)],
        )

    def test_temp_link_into_the_project_is_recorded_as_an_external_link(
        self, project, private_tmp, scratch
    ):
        # Arrange: /tmp/scratch/data -> <project>/data (hand-made)
        link = scratch / "data"
        link.symlink_to(project / "data", target_is_directory=True)
        # Act
        sid = _run_child(project, private_tmp, during=[("read", link / "local.csv")])
        # Assert
        (entry,) = _metadata(sid)["links"]
        assert (
            sorted(_inputs(sid)),
            entry["link"],
            entry.get("external"),
            entry["in_project"],
        ) == (
            [str(project / "data" / "local.csv")],
            str(link),
            True,
            True,
        )

    def test_missing_temp_link_is_external_missing_not_stale(
        self, project, private_tmp, scratch
    ):
        # Arrange
        link = scratch / "data"
        link.symlink_to(project / "data", target_is_directory=True)
        _run_child(project, private_tmp, during=[("read", link / "local.csv")])
        claim = _claim_on_results(project)
        link.unlink()
        # Act
        result = verify_all_claims()
        detail = verify_claim(claim.claim_id)
        # Assert
        assert (result.exit_code, detail["external_missing"]) == (
            EXTERNAL_MISSING,
            [str(link)],
        )

    def test_temp_link_chain_to_a_temp_file_records_link_and_file(
        self, project, private_tmp, scratch
    ):
        # Arrange: /tmp/alias -> /tmp/scratch (both hand-made)
        alias = private_tmp / "alias"
        alias.symlink_to(scratch, target_is_directory=True)
        # Act
        sid = _run_child(project, private_tmp, during=[("read", alias / "raw.csv")])
        # Assert
        links = _metadata(sid)["links"]
        assert (
            _external_inputs(sid),
            [(e["link"], e.get("external")) for e in links],
        ) == ([str(scratch / "raw.csv")], [(str(alias), True)])

    def test_slice_carries_the_temp_link_for_recreation(
        self, project, private_tmp, scratch
    ):
        # Arrange
        link = scratch / "data"
        link.symlink_to(project / "data", target_is_directory=True)
        _run_child(project, private_tmp, during=[("read", link / "local.csv")])
        # Act
        sl = build_slice([str(project / "results.json")])
        # Assert
        assert [
            (e["link"], e.get("external"), e["recreate"]) for e in sl.required_links()
        ] == [(str(link), True, str(project / "data"))]


class TestKnobs:
    def test_exclude_of_tmpdir_restores_temp_is_never_data(
        self, project, private_tmp, scratch
    ):
        # Arrange
        raw = scratch / "raw.csv"
        # Act
        sid = _run_child(
            project,
            private_tmp,
            during=[("read", raw)],
            SCITEX_CLEW_EXTERNAL_EXCLUDE=str(private_tmp),
        )
        # Assert
        assert _external_inputs(sid) == []

    def test_include_of_tmpdir_records_process_tree_files_too(
        self, project, private_tmp
    ):
        # Arrange
        made = private_tmp / "from_subprocess.txt"
        # Act
        sid = _run_child(
            project,
            private_tmp,
            during=[("spawn_write", made), ("read", made)],
            SCITEX_CLEW_EXTERNAL_INCLUDE=str(private_tmp),
        )
        # Assert
        assert _external_inputs(sid) == [str(made)]

    def test_capture_off_records_no_temp_input(self, project, private_tmp, scratch):
        # Arrange
        raw = scratch / "raw.csv"
        # Act
        sid = _run_child(
            project,
            private_tmp,
            during=[("read", raw)],
            SCITEX_CLEW_EXTERNAL_CAPTURE="0",
        )
        # Assert
        assert _external_inputs(sid) == []


class TestPolicyUnit:
    """The real policy with plain injected values (temp roots, start time)."""

    def _policy(self, project, root, start):
        return ExternalPolicy(
            str(project), include=[], exclude=[], temp=[str(root)], process_start=start
        )

    def test_file_older_than_process_start_is_accepted(self, project, private_tmp):
        # Arrange
        f = private_tmp / "old.csv"
        f.write_text("x\n")
        policy = self._policy(project, private_tmp, time.time() + 5)
        # Act
        decision = policy.accepts(str(f))
        # Assert
        assert decision is True

    def test_file_newer_than_process_start_is_rejected(self, project, private_tmp):
        # Arrange
        policy = self._policy(project, private_tmp, time.time() - 5)
        f = private_tmp / "new.csv"
        f.write_text("x\n")
        # Act
        decision = policy.accepts(str(f))
        # Assert
        assert decision is False

    def test_hidden_below_the_temp_root_is_rejected(self, project, private_tmp):
        # Arrange
        f = private_tmp / ".cache" / "state.json"
        f.parent.mkdir()
        f.write_text("{}")
        policy = self._policy(project, private_tmp, time.time() + 5)
        # Act
        decision = policy.accepts(str(f))
        # Assert
        assert decision is False

    def test_temp_root_under_a_dot_dir_still_applies_the_temp_rule(
        self, project, private_tmp
    ):
        # Arrange: $TMPDIR itself under a hidden directory
        root = private_tmp / ".cache" / "tmp"
        root.mkdir(parents=True)
        f = root / "staged.csv"
        f.write_text("x\n")
        policy = self._policy(project, root, time.time() + 5)
        # Act
        decision = policy.accepts(str(f))
        # Assert
        assert decision is True

    def test_the_temp_root_itself_is_not_a_recorded_link(self, project, private_tmp):
        # Arrange
        policy = self._policy(project, private_tmp, time.time() + 5)
        # Act
        decision = policy.records_link(str(private_tmp))
        # Assert
        assert decision is False

    def test_process_start_precedes_now_and_this_test_file(self):
        # Arrange
        interpreter_built = os.stat(sys.executable).st_mtime
        # Act
        start = process_start_time()
        # Assert: started before now, and after the interpreter binary existed
        assert interpreter_built < start < time.time()
