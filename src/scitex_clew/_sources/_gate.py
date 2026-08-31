#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chain-walk source gate — the reusable, pure groundedness check.

``is_grounded`` walks a claim's provenance chain to its root(s) and returns
``True`` iff AT LEAST ONE file in the chain (including the claim's own source)
matches a VALID registered-source manifest entry by ``(path, sha256)``.

This is the laundering guard: a mixed chain with >=1 registered root is
grounded; a chain whose every root is unregistered is not (→ ``unsourced``).

The function is PURE with respect to side effects (it reads the DB and the
already-loaded manifest; it never writes, prints, or touches the CLI), so the
compute-time follow-on (a session-exit observer) can call the identical logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .._chain._routes import resolve_file_dag
from ._manifest import SourcesManifest


def _hash_consistent(recorded: str, pinned: str) -> bool:
    """Prefix-tolerant hash equality.

    DB / claim records recorded before clew-fix-truncated-hash-comparison
    store a truncated (32-char) sha256; records recorded after that fix
    store the full 64-char digest, matching what the manifest pins. Compare
    over the shorter length — a truncated digest is a strict prefix of the
    full one for an untampered file, so this stays correct across the
    truncated/full mix in older DBs. Empty hashes never match.
    """
    if not recorded or not pinned:
        return False
    n = min(len(recorded), len(pinned))
    return recorded[:n].lower() == pinned[:n].lower()


def _resolve_abspath(file_path: str) -> str:
    """Resolve ``file_path`` to an absolute string (best-effort)."""
    try:
        return str(Path(file_path).resolve())
    except OSError:
        return file_path


def collect_chain_files(claim, db) -> List[Tuple[str, str]]:
    """Collect ``(abspath, hash)`` candidates from a claim and its chain.

    Candidates are:

    1. The claim's own ``source_file`` + ``source_hash`` (so a claim pointing
       directly at a registered raw file is grounded by its own node — the
       biomarker case where the chain length is 0).
    2. Every file (any role) recorded for every session in the provenance DAG
       reachable from the claim's ``source_session`` (or the newest producer of
       ``source_file`` when only that is known).

    Reuses the EXISTING file-mediated walk
    (:func:`scitex_clew._chain._routes.resolve_file_dag`) — no custom traversal.
    """
    candidates: List[Tuple[str, str]] = []

    if claim.source_file:
        candidates.append(
            (_resolve_abspath(claim.source_file), claim.source_hash or "")
        )

    session_id = claim.source_session
    if not session_id and claim.source_file:
        producers = db.find_session_by_file(
            _resolve_abspath(claim.source_file), role="output"
        )
        if producers:
            session_id = producers[0]

    if session_id:
        _adjacency, all_ids = resolve_file_dag([session_id], db=db)
        for sid in all_ids:
            for fpath, fhash in db.get_file_hashes(sid).items():
                candidates.append((_resolve_abspath(fpath), fhash))

    return candidates


def is_grounded(claim, manifest: SourcesManifest, db) -> bool:
    """Return ``True`` iff the claim's chain reaches a VALID registered source.

    Parameters
    ----------
    claim : Claim
        The claim (needs ``source_file``, ``source_hash``, ``source_session``).
    manifest : SourcesManifest
        A loaded, tamper-checked manifest. When it has no VALID anchors the
        function returns ``True`` (defensive: nothing to demote against — the
        caller normally gates on ``manifest.active`` before calling).
    db : VerificationDB
        Provides the file-hash + producer lookups the chain walk needs.

    Returns
    -------
    bool
        ``True`` (grounded) iff at least one chain candidate matches a valid
        anchor by absolute path AND hash-consistency; ``False`` (unsourced)
        when every root is unregistered.
    """
    # An UNTRUSTED manifest (unsigned or tampered under an enforcing
    # signing.pub) grounds NOTHING — its anchors can't be trusted, so every
    # claim is unsourced. Checked BEFORE the empty-anchor shortcut so signing
    # enforcement can't be bypassed by an empty/wiped anchor set.
    if not manifest.trusted:
        return False

    anchor_paths = manifest.anchor_paths()
    if not anchor_paths:
        return True

    for abspath, fhash in collect_chain_files(claim, db):
        if abspath in anchor_paths:
            pinned = manifest.pinned_for(abspath)
            if pinned is not None and _hash_consistent(fhash, pinned):
                return True
    return False


# EOF
