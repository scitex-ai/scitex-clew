"""Pytest fixtures and rootdir marker for this package.

An empty conftest.py at tests/ is the canonical SciTeX
convention (audit-project PS208) — it pins the pytest
rootdir and gives downstream fixtures a home.

Subprocess coverage wiring (skill leaf 05_development_06_subprocess-coverage):
when tests spawn child Python interpreters (subprocess.run([sys.executable, ...]),
jupyter nbconvert --execute, etc.), their coverage data is dropped by default
because pytest-cov sets COVERAGE_FILE to a per-test tmp dir before conftest
loads. We force-set (NOT setdefault — that's a silent no-op) COVERAGE_PROCESS_START
+ COVERAGE_FILE at module import time, then write an idempotent .pth shim into
site-packages so coverage.process_startup() fires in every child interpreter.
Store isolation (clew's Postgres migration):
`isolated_store` below is autouse — every test gets its OWN throwaway
PostgreSQL schema, handed to clew through `SCITEX_STORE_DSN`, so the live
fleet store is never touched and no two tests can see each other's rows.
There are no mocks and no fakes: the tests run against a real database.
"""

from __future__ import annotations

import os
import sysconfig
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# The cluster these tests write to.
#
# NOT the per-host loopback. Every `127.0.0.1:55432` in this fleet is a
# READ-ONLY STANDBY (`pg_is_in_recovery()` is true) where `CREATE SCHEMA`
# raises. A suite that defaulted there would SKIP, and a skipped suite
# reports the same green as one that actually checked.
# ---------------------------------------------------------------------------
WRITABLE_DSN = os.environ.get(
    "SCITEX_CLEW_TEST_DSN", "postgresql://scitex-primary:55432/scitex"
)


def _connect():
    """Open an autocommit connection to the writable cluster.

    A missing driver SKIPS — that is a property of the interpreter, not of
    the code under test. Everything else FAILS: an unreachable or read-only
    cluster means these tests did not run, and saying so out loud is the
    whole point.
    """
    psycopg = pytest.importorskip(
        "psycopg", reason="psycopg is not installed in this interpreter"
    )
    try:
        return psycopg.connect(WRITABLE_DSN, connect_timeout=10, autocommit=True)
    except Exception as exc:  # noqa: BLE001 - re-raised as an explicit failure
        pytest.fail(
            f"clew's tests need a WRITABLE PostgreSQL cluster and could not "
            f"reach {WRITABLE_DSN}: {type(exc).__name__}: {exc}\n"
            "This is a FAILURE, not a skip — a skipped store suite is "
            "indistinguishable from a passing one. Override the target with "
            "SCITEX_CLEW_TEST_DSN.",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def _writable_cluster():
    """Assert once per session that the target cluster accepts writes."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_is_in_recovery()")
            (in_recovery,) = cur.fetchone()
    if in_recovery:
        pytest.fail(
            f"{WRITABLE_DSN} is a READ-ONLY STANDBY (pg_is_in_recovery() is "
            "true). CREATE SCHEMA raises there, so every store test would "
            "error or skip. Point SCITEX_CLEW_TEST_DSN at the primary.",
            pytrace=False,
        )
    return WRITABLE_DSN


@pytest.fixture(autouse=True)
def isolated_store(_writable_cluster):
    """Give this test its own PostgreSQL schema, and drop it afterwards.

    clew resolves its stores through `scitex_dev.store.host_store()`, whose
    single switch is `SCITEX_STORE_DSN`. Setting that to a DSN carrying
    `options=-csearch_path=<schema>` puts every table clew creates inside a
    throwaway schema; `DROP SCHEMA ... CASCADE` then removes the lot.

    `reset_db()` runs on both edges because `get_db()` caches the global
    `VerificationDB` for the life of the process, and a cached instance
    would keep answering from the PREVIOUS test's schema.
    """
    from scitex_clew._db import reset_db

    schema = f"clewtest_{uuid.uuid4().hex[:16]}"
    previous = os.environ.get("SCITEX_STORE_DSN")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')

    os.environ["SCITEX_STORE_DSN"] = (
        f"{WRITABLE_DSN}?options={quote(f'-csearch_path={schema}', safe='')}"
    )
    reset_db()
    try:
        yield schema
    finally:
        reset_db()
        if previous is None:
            os.environ.pop("SCITEX_STORE_DSN", None)
        else:
            os.environ["SCITEX_STORE_DSN"] = previous
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

# Pin coverage data file at the repo root and point process_startup at our
# pyproject so child interpreters configure themselves correctly. Force-set
# (not setdefault) because pytest-cov has already populated COVERAGE_FILE by
# the time this conftest is imported.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent `.pth` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    `coverage.process_startup()`.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_scitex_clew_subprocess_coverage.pth"
    shim = (
        "import os, coverage\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    coverage.process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently skip —
        # local dev venvs are writable and that's where this matters.
        pass


_ensure_subprocess_coverage_shim()
