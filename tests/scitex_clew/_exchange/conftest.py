"""One real clew project for this test package, in its own PostgreSQL schema.

Building the project runs two real ``@session`` analyses in child
interpreters, so it is built once for the package. ``isolated_store`` is
therefore overridden at PACKAGE scope (a throwaway schema, created then
dropped), like the evidence-provider tests do per module. Tests that change files work on a COPY of
the project (:func:`project_copy`), never on the shared one.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from tests.conftest import WRITABLE_DSN, _connect

from ._bundle_project import build_project


@pytest.fixture(scope="package", autouse=True)
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


@pytest.fixture(scope="package")
def bundle_project(isolated_store, tmp_path_factory) -> Path:
    """The built project root (see :mod:`._bundle_project`)."""
    journal = tmp_path_factory.mktemp("clew-journal")
    return build_project(tmp_path_factory.mktemp("bundle"), journal)


@pytest.fixture(scope="package")
def signing_key(tmp_path_factory) -> Path:
    """A per-package Ed25519 private key file, made by the real keygen path."""
    from scitex_clew._exchange import generate_private_key_file

    path = tmp_path_factory.mktemp("keys") / "bundle.key"
    generate_private_key_file(path)
    return path


@pytest.fixture(scope="package")
def signed_bundle(bundle_project, signing_key) -> Path:
    """The project's bundle, exported from the store and signed."""
    from scitex_clew._exchange import export_bundle, load_signer

    path, _doc = export_bundle(bundle_project, signer=load_signer(signing_key))
    return path


@pytest.fixture
def project_copy(bundle_project, signed_bundle, tmp_path) -> Path:
    """A private copy of the project (with its bundle) a test may change."""
    dest = tmp_path / bundle_project.name
    shutil.copytree(bundle_project, dest, symlinks=True)
    return dest


# EOF
