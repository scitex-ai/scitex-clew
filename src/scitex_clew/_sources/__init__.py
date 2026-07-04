#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered-source gate — hash-pinned trust whitelist + chain-walk grounding.

Public surface (re-exported at ``scitex_clew`` top level):

* :func:`register_source` / :func:`unregister_source` / :func:`list_sources`
  — the human-run manifest writers/reader.
* :func:`load_sources_manifest` / :func:`resolve_sources_path` — read side.
* :func:`is_grounded` — the reusable pure chain-walk gate.
"""

from __future__ import annotations

from ._gate import collect_chain_files, is_grounded
from ._manifest import (
    SOURCES_SCHEMA,
    SourceEntry,
    SourcesManifest,
    full_sha256,
    load_sources_manifest,
    resolve_sources_path,
    verify_signature,
)
from ._writer import list_sources, register_source, unregister_source

__all__ = [
    "SOURCES_SCHEMA",
    "SourceEntry",
    "SourcesManifest",
    "full_sha256",
    "load_sources_manifest",
    "resolve_sources_path",
    "verify_signature",
    "is_grounded",
    "collect_chain_files",
    "register_source",
    "unregister_source",
    "list_sources",
]

# EOF
