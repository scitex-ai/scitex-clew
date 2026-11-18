"""One real clew project per test module, in its own PostgreSQL schema.

Building the project runs two real ``@session`` analyses and a registration
in child interpreters, so it is built once per module rather than once per
test. ``isolated_store`` is therefore overridden here at MODULE scope: the
module gets its own throwaway schema (created, then dropped), exactly like the
root conftest's per-test schema, and no other module can see its rows. The
tests in this directory only read the project (``verify`` rewrites each
claim's stored status, idempotently).
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import quote

import pytest

from tests.conftest import WRITABLE_DSN, _connect

from ._clew_project import build_project


@pytest.fixture(scope="module", autouse=True)
def isolated_store(_writable_cluster):
    from scitex_clew._db import reset_db

    schema = f"clewtest_{uuid.uuid4().hex[:16]}"
    previous = os.environ.get("SCITEX_STORE_DSN")
    with _connect() as conn, conn.cursor() as cur:
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
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture(scope="module")
def journal_dir(tmp_path_factory):
    """The recording-journal directory the project's child runs write to."""
    return tmp_path_factory.mktemp("clew-journal")


@pytest.fixture(scope="module")
def clew_project(isolated_store, tmp_path_factory, journal_dir):
    """The built project root (see :mod:`._clew_project`)."""
    return build_project(tmp_path_factory.mktemp("evidence"), journal_dir)


@pytest.fixture(scope="module")
def report(clew_project):
    """The adapter's report on the built project (every claim, with graphs)."""
    from scitex_clew._evidence_provider import EvidenceEntry

    return EvidenceEntry.adapter.evidence_report(str(clew_project), None, {})


@pytest.fixture(scope="module")
def by_id(report):
    return {c["claim_id"]: c for c in report["claims"]}
