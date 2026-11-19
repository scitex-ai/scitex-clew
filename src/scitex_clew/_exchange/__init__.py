#!/usr/bin/env python3
"""Clew evidence EXCHANGE FORMAT: a portable, signed, versioned evidence bundle.

A clew project's runs and claims live in the host store, which a third party
(a journal, a reviewer, CI elsewhere) cannot reach. The evidence bundle
carries them WITH the repository snapshot, so anyone can verify and re-run
the evidence from a checkout alone:

* ``<project_root>/.scitex/clew/evidence-bundle.json`` — committed with the
  repo (schema ``scitex-clew.evidence-bundle`` 1.0.0, JSON Schema shipped in
  this package: :data:`BUNDLE_SCHEMA_PATH`);
* :func:`export_bundle` — build it from the store (``clew bundle export``),
  optionally Ed25519-signed (:mod:`._signing`, pluggable Signer/Verifier);
* :func:`verify_bundle` — schema, signature and every recorded file hash
  against a checkout (``clew bundle verify``), store-free;
* :func:`rerun_bundle` — re-execute the recorded runs in a temporary copy and
  recompute every claim (``clew bundle rerun``), store-free. It EXECUTES
  PROJECT CODE: run it in an isolated container.

Formats are versioned by ``schema_version``; consumers ignore unknown keys.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._canonical import canonical_bytes, sha256_file
from ._export import BUNDLE_SCHEMA, BUNDLE_SCHEMA_VERSION, build_bundle
from ._rerun import RERUN_SCHEMA, RERUN_SCHEMA_VERSION, rerun_bundle
from ._schema import (
    BUNDLE_SCHEMA_ID,
    BUNDLE_SCHEMA_PATH,
    RERUN_SCHEMA_ID,
    RERUN_SCHEMA_PATH,
    load_schema,
    schema_errors,
)
from ._signing import (
    Ed25519Signer,
    Ed25519Verifier,
    Signer,
    Verifier,
    generate_private_key_file,
    key_id_of,
    load_signer,
    register_verifier,
    sign_document,
    verify_document,
)
from ._verify import load_bundle, verify_bundle

__all__ = [
    "BUNDLE_SCHEMA",
    "BUNDLE_SCHEMA_ID",
    "BUNDLE_SCHEMA_PATH",
    "BUNDLE_SCHEMA_VERSION",
    "DEFAULT_BUNDLE_RELPATH",
    "RERUN_SCHEMA",
    "RERUN_SCHEMA_ID",
    "RERUN_SCHEMA_PATH",
    "RERUN_SCHEMA_VERSION",
    "Ed25519Signer",
    "Ed25519Verifier",
    "Signer",
    "Verifier",
    "build_bundle",
    "canonical_bytes",
    "default_bundle_path",
    "export_bundle",
    "generate_private_key_file",
    "key_id_of",
    "load_bundle",
    "load_schema",
    "load_signer",
    "register_verifier",
    "rerun_bundle",
    "schema_errors",
    "sha256_file",
    "sign_document",
    "verify_bundle",
    "verify_document",
    "write_bundle",
]

#: Where a project's bundle lives, relative to its root (meant to be committed).
DEFAULT_BUNDLE_RELPATH = ".scitex/clew/evidence-bundle.json"


def default_bundle_path(project_root: str | Path) -> Path:
    """``<project_root>/.scitex/clew/evidence-bundle.json``."""
    return Path(project_root).expanduser().resolve() / DEFAULT_BUNDLE_RELPATH


def write_bundle(document: dict, path: str | Path) -> Path:
    """Write ``document`` as pretty, key-sorted UTF-8 JSON (stable diffs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def export_bundle(
    project_root: str | Path,
    out: str | Path | None = None,
    *,
    signer: Signer | None = None,
    all_runs: bool = False,
) -> tuple[Path, dict]:
    """Build (and sign, when ``signer`` is given) the bundle; write it to ``out``.

    ``out`` defaults to :func:`default_bundle_path`. Returns ``(path, document)``.
    """
    document = build_bundle(project_root, all_runs=all_runs)
    if signer is not None:
        document = sign_document(document, signer)
    target = Path(out) if out is not None else default_bundle_path(project_root)
    return write_bundle(document, target), document


# EOF
