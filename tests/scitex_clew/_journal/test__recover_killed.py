#!/usr/bin/env python3
"""Kill-durable recording: REAL processes killed mid-run, REAL store. No mocks.

Each child interpreter runs a real recorded session (clew's session hooks, as
``@stx.session`` drives them, with the ``open()`` capture on) against a
private PostgreSQL schema, and is ended the way agent harnesses end runs:
``SIGKILL`` (nothing runs), ``SIGTERM``, or an interpreter exit without
closing. The rows recovered from its journal are compared with what an
identical CLEAN run records.

Each scenario runs ONCE per class (child processes are the expensive part)
and records what it observed; each test then checks one fact of it.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import pytest
from scitex_clew._db import reset_db
from scitex_clew._db._core import VerificationDB
from scitex_clew._hash import hash_file
from scitex_clew._journal import JOURNAL_DIR_ENV, journal_dir, recover_journals

_CHILD = r"""
import sys, time
from pathlib import Path
mode, root, sid, n = sys.argv[1], Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
from scitex_clew._observers import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker
on_session_start(sid, script_path=str(root / "scripts" / "run.py"),
                 metadata={"project_root": str(root)})
tracker = get_tracker()
for i in range(n):
    path = root / "data" / f"in{i:04d}.txt"
    if i % 2 == 0:
        with open(path) as handle:      # captured by the open() audit hook
            handle.read()
    else:
        tracker.record_input(path)      # explicit (as stx.io.load does)
    print(f"in {i}", flush=True)
(root / "out.txt").write_text("result\n")
tracker.record_output(root / "out.txt")
(root / "partial.txt").write_text("half")   # captured write, hashed at close
print("READY", flush=True)
if mode == "close":
    on_session_close(status="success", exit_code=0)
elif mode == "hang":
    time.sleep(600)
elif mode == "wait":
    sys.stdin.readline()
    on_session_close(status="success", exit_code=0)
# mode "exit": the interpreter exits with the session still open
"""

N_INPUTS = 6
N_FILES = 400
_CLI = "from scitex_clew._cli._main import main; main()"


# ----------------------------------------------------------------- harness


class Lab:
    """A project, a private store schema and a journal dir for one scenario."""

    def __init__(self, base: Path, dsn: str):
        self.base = base
        self.dsn = dsn
        self.scope = f"killtest-{uuid.uuid4().hex[:12]}"
        self.root = base / "proj"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / ".git").mkdir()
        (self.root / "scripts" / "run.py").write_text(_CHILD)
        for i in range(N_FILES):
            (self.root / "data" / f"in{i:04d}.txt").write_text(f"value {i}\n")
        self.journals = base / "journal"

    def env(self, **extra) -> dict[str, str]:
        """An explicit allowlist — never this process's whole environment."""
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ["HOME"],
            "LANG": "C.UTF-8",
            "SCITEX_STORE_DSN": self.dsn,
            "SCITEX_CLEW_PROJECT": self.scope,
            JOURNAL_DIR_ENV: str(self.journals),
            "SCITEX_DIR": str(self.base / "scitex-dir"),
        }
        env.update(extra)
        return env

    def start(self, mode: str, sid: str, n: int = N_INPUTS) -> subprocess.Popen:
        argv = [sys.executable, str(self.root / "scripts" / "run.py"), mode]
        return subprocess.Popen(
            argv + [str(self.root), sid, str(n)],
            cwd=self.root,
            env=self.env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def clean(self, n: int = N_INPUTS) -> str:
        sid = f"clean-{uuid.uuid4().hex[:8]}"
        proc = self.start("close", sid, n)
        _, err = proc.communicate(timeout=120)
        if proc.returncode != 0:
            raise AssertionError(err)
        return sid

    def kill(self, sig=signal.SIGKILL, n: int = N_INPUTS, marker: str = "READY"):
        """Run a session until ``marker``, then end it with ``sig``."""
        sid = f"killed-{uuid.uuid4().hex[:8]}"
        proc = self.start("hang", sid, n)
        wait_for(proc, marker)
        proc.send_signal(sig)
        proc.wait(timeout=60)
        proc.stdout.close()
        proc.stderr.close()
        proc.stdin.close()
        return sid, proc.returncode

    def db(self) -> VerificationDB:
        return VerificationDB(project=self.scope)

    def rows(self, sid: str) -> set[tuple[str, str, str]]:
        db = self.db()
        try:
            return {
                (r["file_path"], r["role"], r["hash"])
                for r in db.session_file_records(sid)
            }
        finally:
            db.close()

    def rows_before_close(self, sid: str) -> set[tuple[str, str, str]]:
        """A closed run's rows minus what only a CLOSE records: the bytes of
        files it opened for writing are hashed at close (``partial.txt``),
        so a run killed before close cannot have them."""
        partial = str((self.root / "partial.txt").resolve())
        return {row for row in self.rows(sid) if row[0] != partial}

    def run(self, sid: str) -> dict:
        db = self.db()
        try:
            return db.get_run(sid)
        finally:
            db.close()

    def journal_files(self) -> list[Path]:
        directory = journal_dir()
        return sorted(directory.glob("*.jsonl")) if directory.is_dir() else []

    def cli(self, *args: str, **env) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", _CLI, *args],
            env=self.env(**env),
            capture_output=True,
            text=True,
            timeout=120,
        )


def wait_for(proc, marker: str) -> None:
    for line in proc.stdout:
        if line.strip() == marker:
            return
    raise AssertionError(f"child ended before {marker!r}: {proc.stderr.read()}")


@contextmanager
def lab(base: Path, cluster_dsn: str):
    """A private schema + journal dir, active in this process's env."""
    import psycopg

    schema = f"clewkill_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(cluster_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    dsn = f"{cluster_dsn}?options={quote(f'-csearch_path={schema}', safe='')}"
    names = ("SCITEX_STORE_DSN", JOURNAL_DIR_ENV, "SCITEX_CLEW_PROJECT")
    saved = {name: os.environ.get(name) for name in names}
    env_lab = Lab(base, dsn)
    os.environ.update(
        {
            "SCITEX_STORE_DSN": dsn,
            JOURNAL_DIR_ENV: str(env_lab.journals),
            "SCITEX_CLEW_PROJECT": env_lab.scope,
        }
    )
    reset_db()
    try:
        yield env_lab
    finally:
        reset_db()
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        with psycopg.connect(cluster_dsn, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


# --------------------------------------------------------------- scenarios


@pytest.fixture(scope="class")
def sigkill(tmp_path_factory, _writable_cluster):
    """A clean run, then the same run SIGKILLed after READY, then recovery."""
    with lab(tmp_path_factory.mktemp("sigkill"), _writable_cluster) as env:
        clean = env.clean()
        killed, code = env.kill()
        before = {"status": env.run(killed)["status"], "rows": env.rows(killed)}
        reports = recover_journals()
        run = env.run(killed)
        yield {
            "code": code,
            "before": before,
            "reports": reports,
            "clean": env.rows_before_close(clean),
            "recovered": env.rows(killed),
            "run": run,
            "meta": json.loads(run["metadata"])["clew_recovery"],
            "partial": str((env.root / "partial.txt").resolve()),
            "journals": env.journal_files(),
            "again": recover_journals(),
        }


class TestSigkill:
    def test_child_died_of_sigkill(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["code"] == -signal.SIGKILL

    def test_before_recovery_no_row_reached_the_store(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["before"]["rows"] == set()

    def test_before_recovery_the_run_is_running(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["before"]["status"] == "running"

    def test_recovery_reports_the_killed_session(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert len(observed["reports"]) == 1

    def test_recovered_rows_equal_a_clean_run(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["recovered"] == observed["clean"]

    def test_recovered_rows_cover_every_input_and_the_output(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert len(observed["recovered"]) == N_INPUTS + 1

    def test_run_is_closed_as_killed(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["run"]["status"] == "killed"

    def test_killed_run_has_no_exit_code(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["run"]["exit_code"] is None

    def test_unhashed_partial_write_is_listed(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["meta"]["unhashed_writes"] == [observed["partial"]]

    def test_journal_is_deleted(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["journals"] == []

    def test_second_recovery_finds_nothing(self, sigkill):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigkill
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["again"] == []


@pytest.fixture(scope="class")
def mid_loop(tmp_path_factory, _writable_cluster):
    """SIGKILL while the run is still reading inputs (after input 149)."""
    with lab(tmp_path_factory.mktemp("midloop"), _writable_cluster) as env:
        clean = env.clean(n=N_FILES)
        killed, _ = env.kill(n=N_FILES, marker="in 149")
        recover_journals()
        recovered = env.rows(killed)
        yield {
            "clean": env.rows_before_close(clean),
            "recovered": recovered,
            "inputs": {Path(p) for p, role, _ in recovered if role == "input"},
            "before_kill": {
                (env.root / "data" / f"in{i:04d}.txt").resolve() for i in range(150)
            },
        }


class TestKillMidLoop:
    def test_every_recovered_row_is_a_row_a_clean_run_records(self, mid_loop):
        # Arrange: the scenario ran once, in its class fixture
        observed = mid_loop
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["recovered"] <= observed["clean"]

    def test_every_input_recorded_before_the_kill_is_recovered(self, mid_loop):
        # Arrange: the scenario ran once, in its class fixture
        observed = mid_loop
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["before_kill"] <= observed["inputs"]


@pytest.fixture(scope="class")
def replay_twice(tmp_path_factory, _writable_cluster):
    """Recover a journal, put the same journal back, recover it again."""
    with lab(tmp_path_factory.mktemp("twice"), _writable_cluster) as env:
        producer = f"producer-{uuid.uuid4().hex[:8]}"
        src = str((env.root / "data" / "in0001.txt").resolve())
        db = env.db()
        db.add_run(producer, script_path="make.py")
        db.add_file_hash(
            producer, src, hash_file(src), "output", recorded_at="2000-01-01T00:00:00"
        )
        db.finish_run(producer)
        killed, _ = env.kill()
        (journal,) = env.journal_files()
        backup = env.base / "journal.copy"
        shutil.copy(journal, backup)
        recover_journals()
        first = {
            "rows": env.rows(killed),
            "count": len(db.session_file_records(killed)),
            "parents": db.get_parents(killed),
            "run": env.run(killed),
        }
        shutil.copy(backup, journal)
        (again,) = recover_journals()
        yield {
            "producer": producer,
            "first": first,
            "again": again,
            "rows": env.rows(killed),
            "count": len(db.session_file_records(killed)),
            "parents": db.get_parents(killed),
            "run": env.run(killed),
        }
        db.close()


class TestReplayIsIdempotent:
    def test_second_replay_did_replay_rows(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["again"]["rows_replayed"] > 0

    def test_second_replay_saw_the_run_already_killed(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["again"]["status_before"] == "killed"

    def test_rows_are_unchanged(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["rows"] == observed["first"]["rows"]

    def test_no_duplicate_rows(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["count"] == observed["first"]["count"]

    def test_producer_bound_once(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["parents"] == [observed["producer"]]

    def test_finish_time_unchanged(self, replay_twice):
        # Arrange: the scenario ran once, in its class fixture
        observed = replay_twice
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert (
            observed["run"]["finished_at"]
            == observed["first"]["run"]["finished_at"]
        )


@pytest.fixture(scope="class")
def sigterm(tmp_path_factory, _writable_cluster):
    """SIGTERM after READY: the handler closes the run before the process dies."""
    with lab(tmp_path_factory.mktemp("sigterm"), _writable_cluster) as env:
        clean = env.clean()
        killed, code = env.kill(sig=signal.SIGTERM)
        # Read BEFORE any recovery call: the handler alone must have done it.
        run = env.run(killed)
        yield {
            "code": code,
            "run": run,
            "meta": json.loads(run["metadata"])["clew_recovery"],
            "rows": env.rows(killed),
            "clean": env.rows_before_close(clean),
            "journals": env.journal_files(),
        }


class TestSigterm:
    def test_process_still_dies_of_sigterm(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["code"] == -signal.SIGTERM

    def test_run_is_closed_as_killed(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["run"]["status"] == "killed"

    def test_exit_code_is_minus_signum(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["run"]["exit_code"] == -signal.SIGTERM

    def test_signal_is_named_in_metadata(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["meta"]["signal"] == "SIGTERM"

    def test_rows_equal_a_clean_run(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["rows"] == observed["clean"]

    def test_journal_is_deleted(self, sigterm):
        # Arrange: the scenario ran once, in its class fixture
        observed = sigterm
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["journals"] == []


@pytest.fixture(scope="class")
def unclosed_exit(tmp_path_factory, _writable_cluster):
    """The interpreter exits normally with the session still open."""
    with lab(tmp_path_factory.mktemp("exit"), _writable_cluster) as env:
        clean = env.clean()
        sid = f"open-{uuid.uuid4().hex[:8]}"
        proc = env.start("exit", sid)
        _, err = proc.communicate(timeout=120)
        yield {
            "code": proc.returncode,
            "err": err,
            "run": env.run(sid),
            "rows": env.rows(sid),
            "clean": env.rows(clean),
            "journals": env.journal_files(),
        }


class TestExitWithoutClose:
    def test_process_exits_cleanly(self, unclosed_exit):
        # Arrange: the scenario ran once, in its class fixture
        observed = unclosed_exit
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["code"] == 0, observed["err"]

    def test_run_is_incomplete(self, unclosed_exit):
        # Arrange: the scenario ran once, in its class fixture
        observed = unclosed_exit
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["run"]["status"] == "incomplete"

    def test_rows_equal_a_clean_run(self, unclosed_exit):
        # Arrange: the scenario ran once, in its class fixture
        observed = unclosed_exit
        # Act: nothing more to run; read what the scenario observed
        # Assert
        # A clean exit also hashes the captured write (partial.txt).
        assert observed["rows"] == observed["clean"]

    def test_journal_is_deleted(self, unclosed_exit):
        # Arrange: the scenario ran once, in its class fixture
        observed = unclosed_exit
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["journals"] == []


@pytest.fixture(scope="class")
def triggers(tmp_path_factory, _writable_cluster):
    """Recovery from a new session's start, from the CLI, and across stores."""
    with lab(tmp_path_factory.mktemp("triggers"), _writable_cluster) as env:
        by_start, _ = env.kill()
        env.clean()  # a NEW recorded run in a new process
        status_after_start = env.run(by_start)["status"]

        by_cli, _ = env.kill()
        dry = env.cli("--json", "recover-journals", "--dry-run")
        real = env.cli("--json", "recover-journals")

        other_store, _ = env.kill()
        other = env.cli(
            "--json", "recover-journals", SCITEX_STORE_DSN=env.dsn + "-another-store"
        )
        yield {
            "status_after_start": status_after_start,
            "by_cli": by_cli,
            "dry": json.loads(dry.stdout)["recovered"],
            "real": json.loads(real.stdout)["recovered"],
            "cli_status": env.run(by_cli)["status"],
            "other": json.loads(other.stdout)["recovered"],
            "other_status": env.run(other_store)["status"],
            "journals": env.journal_files(),
        }


class TestRecoveryTriggers:
    def test_next_session_start_recovers_a_killed_run(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["status_after_start"] == "killed"

    def test_cli_dry_run_reports_the_killed_session(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert [r["session_id"] for r in observed["dry"]] == [observed["by_cli"]]

    def test_cli_replays_and_closes_it(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert [r["status"] for r in observed["real"]] == ["killed"]

    def test_cli_recovery_reaches_the_store(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["cli_status"] == "killed"

    def test_another_store_replays_nothing(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["other"] == []

    def test_another_store_leaves_the_run_running(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["other_status"] == "running"

    def test_another_store_leaves_the_journal(self, triggers):
        # Arrange: the scenario ran once, in its class fixture
        observed = triggers
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert len(observed["journals"]) == 1


@pytest.fixture(scope="class")
def concurrent(tmp_path_factory, _writable_cluster):
    """Two LIVE sessions and one SIGKILLed one; recover; then the live close."""
    with lab(tmp_path_factory.mktemp("concurrent"), _writable_cluster) as env:
        live = [f"live-{i}-{uuid.uuid4().hex[:6]}" for i in range(2)]
        procs = [env.start("wait", sid) for sid in live]
        for proc in procs:
            wait_for(proc, "READY")
        killed, _ = env.kill()
        reports = recover_journals()
        during = {
            "status": [env.run(s)["status"] for s in live],
            "journals": len(env.journal_files()),
        }
        codes = []
        for proc in procs:
            proc.communicate("\n", timeout=120)
            codes.append(proc.returncode)
        yield {
            "killed": killed,
            "reports": [r["session_id"] for r in reports],
            "during": during,
            "codes": codes,
            "after": [env.run(s)["status"] for s in live],
            "rows": [*(env.rows_before_close(s) for s in live), env.rows(killed)],
            "journals": env.journal_files(),
        }


class TestConcurrentSessions:
    def test_only_the_dead_session_is_recovered(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["reports"] == [observed["killed"]]

    def test_live_sessions_stay_running_during_recovery(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["during"]["status"] == ["running", "running"]

    def test_live_journals_are_untouched(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["during"]["journals"] == 2

    def test_live_sessions_exit_cleanly(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["codes"] == [0, 0]

    def test_live_sessions_close_as_success(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["after"] == ["success", "success"]

    def test_all_three_recorded_the_same_rows(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        first, second, killed = observed["rows"]
        assert first == second == killed

    def test_no_journal_is_left(self, concurrent):
        # Arrange: the scenario ran once, in its class fixture
        observed = concurrent
        # Act: nothing more to run; read what the scenario observed
        # Assert
        assert observed["journals"] == []


# EOF
