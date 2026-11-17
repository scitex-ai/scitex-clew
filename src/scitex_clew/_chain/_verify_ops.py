#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_verify_ops.py
"""Core file and run verification logic."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

from .._db import get_db
from .._hash import hash_like, hashes_match
from ._archive_lookup import hash_archived_file
from ._types import (
    FileVerification,
    RunVerification,
    VerificationStatus,
)


def verify_file(
    path: str | Path,
    expected_hash: str,
    role: str = "unknown",
    hash_cache: dict[str, str] | None = None,
    frozen: bool = False,
) -> FileVerification:
    """Verify a single file against expected hash.

    If the loose file is gone but its enclosing session dir was compressed to
    an ancestor ``<dir>.tar.gz`` (``scitex.session`` archive mode), the file
    is read+hashed from inside the archive instead of being reported MISSING.
    This keeps provenance verifiable after the inode-saving compression — the
    archived bytes are byte-identical to the recorded ones.

    Parameters
    ----------
    path : str or Path
        Path to the file
    expected_hash : str
        Expected hash value
    role : str, optional
        Role of the file (input, output, script)
    hash_cache : dict or None, optional
        Per-pass cache (resolved-path -> hash) threaded from the top-level
        verify entry point. When provided, each file is hashed at most once
        within the pass; subsequent references reuse the cached value.
    frozen : bool, optional
        When True, skip re-hashing and trust the recorded hash.  The file's
        *existence* is still checked: a frozen file that is absent on disk is
        still reported MISSING (frozen means "trust the hash without
        re-reading", not "ignore missing files").  Returns a FileVerification
        with ``status=VERIFIED`` and ``frozen=True`` — never silently rendered
        as a normal verified file; callers and renderers must surface the
        frozen state (frozen blue #0072b2 / "FROZEN" label — color-only, no
        glyph).

    Returns
    -------
    FileVerification
        Verification result
    """
    path = Path(path)
    path_str = str(path)

    # Frozen short-circuit: trust the recorded hash without re-reading the
    # file.  We still check existence so a genuinely missing frozen file is
    # not silently swallowed — the user needs to know the data is gone even
    # if they opted out of re-hashing.
    if frozen:
        if not path.exists() and hash_archived_file(path) is None:
            return FileVerification(
                path=path_str,
                role=role,
                expected_hash=expected_hash,
                current_hash=None,
                status=VerificationStatus.MISSING,
                frozen=True,
            )
        # File present (or archived): trust the stored hash, no re-read.
        return FileVerification(
            path=path_str,
            role=role,
            expected_hash=expected_hash,
            current_hash=expected_hash,
            status=VerificationStatus.VERIFIED,
            frozen=True,
        )

    if path.exists():
        # same scheme as recorded (a notebook code hash re-hashes the code)
        current_hash = hash_like(path, expected_hash, hash_cache=hash_cache)
    else:
        # Loose file absent — try to read it from an ancestor session archive
        # (transparent .tar.gz support). None means truly gone.
        current_hash = hash_archived_file(path)
        if current_hash is None:
            return FileVerification(
                path=path_str,
                role=role,
                expected_hash=expected_hash,
                current_hash=None,
                status=VerificationStatus.MISSING,
            )

    # Full equality; only the legacy 32-char truncated width is tolerated.
    matches = hashes_match(expected_hash, current_hash)

    return FileVerification(
        path=path_str,
        role=role,
        expected_hash=expected_hash,
        current_hash=current_hash,
        status=VerificationStatus.VERIFIED if matches else VerificationStatus.MISMATCH,
    )


#: ``expected_hash`` / ``current_hash`` prefix of a symlink check.
LINK_PREFIX = "symlink->"


def verify_link(entry: dict, role: str = "input") -> FileVerification:
    """Check a recorded symlink (see :mod:`scitex_clew._links`, #192).

    VERIFIED when the link still exists and still resolves to the recorded
    target; MISSING when the link itself is gone; MISMATCH when it is no
    longer a link or now resolves elsewhere. Resolution is compared, not the
    link text: a slice recreates an absolute in-project link as a relative
    one. The target file's bytes are checked by its own file row.
    """
    import os

    link = entry["link"]
    expected = f"{LINK_PREFIX}{entry.get('resolved')}"
    if os.path.islink(link):
        current = f"{LINK_PREFIX}{os.path.realpath(link)}"
        status = (
            VerificationStatus.VERIFIED
            if current == expected
            else VerificationStatus.MISMATCH
        )
    elif os.path.lexists(link):
        current, status = f"not a symlink: {link}", VerificationStatus.MISMATCH
    else:
        current, status = None, VerificationStatus.MISSING
    return FileVerification(
        path=link,
        role=role,
        expected_hash=expected,
        current_hash=current,
        status=status,
        link=True,
    )


def _link_checks(run_info, input_hashes, output_hashes) -> list[FileVerification]:
    """Link checks for the run's recorded symlinks reaching the checked files."""
    from ._slice_records import run_metadata_of

    checks = []
    for entry in run_metadata_of(run_info).get("links") or []:
        if not isinstance(entry, dict) or not entry.get("link"):
            continue
        files = set(entry.get("files") or [])
        if files & set(input_hashes):
            checks.append(verify_link(entry, role="input"))
        elif files & set(output_hashes):
            checks.append(verify_link(entry, role="output"))
    return checks


def _resolve_target(db, target: str) -> str | None:
    """Resolve target (session_id, script path, or artifact path) to session_id."""
    # Try as session_id
    if db.get_run(target):
        return target

    # Resolve to absolute path
    resolved = str(Path(target).resolve())

    # Try as script path
    for run in db.list_runs(limit=100):
        if run.get("script_path") == resolved:
            return run["session_id"]

    # Try as artifact (output) path: the producer of the bytes on disk now.
    from ._routes import current_hash_or_none, resolve_producer

    return resolve_producer(db, resolved, current_hash_or_none(resolved))


#: Recorded run statuses that mean the execution did not complete. Such a
#: run's files are not evidence, whatever their hashes say.
FAILED_RUN_STATUSES = frozenset({"failed", "error"})


def run_failed(run_info: dict | None) -> bool:
    """True when the recorded execution status says the run failed."""
    status = (run_info or {}).get("status")
    return str(status).lower() in FAILED_RUN_STATUSES if status else False


def verify_run(
    target: str,
    propagate: bool = True,
    collapse_suspect: bool = False,
    hash_cache: dict[str, str] | None = None,
    slice_files: dict[str, set[str]] | None = None,
) -> RunVerification:
    """Verify a session run by checking all file hashes.

    Parameters
    ----------
    target : str
        Session ID, script path, or artifact path
    propagate : bool
        If True, mark as failed if any upstream input has failed verification.
    collapse_suspect : bool
        Backward-compatibility knob for the original 2-state output:
        when True the new SUSPECT state ("upstream failed but every local
        file verifies on its own") is folded back into MISMATCH, exactly
        matching the pre-SUSPECT behaviour. Default is False so callers
        opting into the 3-state DAG colouring get SUSPECT surfaced
        without further changes.
    hash_cache : dict or None, optional
        Per-pass cache (resolved-path -> hash) threaded from the top-level
        verify entry point. When provided, each file is hashed at most once
        within the pass; subsequent references reuse the cached value.
    slice_files : dict, optional
        ``{"input": {paths}, "output": {paths}}`` from a minimal slice
        (:meth:`ProvenanceSlice.run_files`): only these recorded files (plus
        the script) are checked, and upstream-failure propagation considers
        only parents bound through the kept inputs. ``None`` checks every
        recorded file (run-level closure).

    Returns
    -------
    RunVerification
        Verification result
    """
    db = get_db()

    # Resolve target to session_id
    session_id = _resolve_target(db, target)
    if not session_id:
        return RunVerification(
            session_id=target,
            script_path=None,
            status=VerificationStatus.UNKNOWN,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
        )

    # Get run info
    run_info = db.get_run(session_id)
    if not run_info:
        return RunVerification(
            session_id=session_id,
            script_path=None,
            status=VerificationStatus.UNKNOWN,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
        )

    # Get all file hashes
    input_hashes = db.get_file_hashes(session_id, role="input")
    output_hashes = db.get_file_hashes(session_id, role="output")
    if slice_files is not None:
        keep_in = slice_files.get("input", set())
        keep_out = slice_files.get("output", set())
        input_hashes = {p: h for p, h in input_hashes.items() if p in keep_in}
        output_hashes = {p: h for p, h in output_hashes.items() if p in keep_out}

    # Get frozen file sets (additive helper, no change to existing get_file_hashes API)
    frozen_inputs = db.get_frozen_files(session_id, role="input")
    frozen_outputs = db.get_frozen_files(session_id, role="output")
    external_inputs = db.get_external_files(session_id, role="input")

    # Verify each file
    file_verifications = []
    upstream_failed = False

    for path, expected in input_hashes.items():
        fv = verify_file(
            path,
            expected,
            role="input",
            hash_cache=hash_cache,
            frozen=path in frozen_inputs,
        )
        fv.external = path in external_inputs
        file_verifications.append(fv)

        # Check if upstream session that produced this input has failed
        # A frozen file that verifies (trusted) does NOT trigger upstream_failed.
        if propagate and not fv.is_verified:
            upstream_failed = True

    for path, expected in output_hashes.items():
        file_verifications.append(
            verify_file(
                path,
                expected,
                role="output",
                hash_cache=hash_cache,
                frozen=path in frozen_outputs,
            )
        )

    # The symlinks the run went through to reach those files (#192): an
    # input link that vanished or was retargeted is a changed input.
    for fv in _link_checks(run_info, input_hashes, output_hashes):
        file_verifications.append(fv)
        if propagate and fv.role == "input" and not fv.is_verified:
            upstream_failed = True

    # Verify script if present
    if run_info.get("script_path") and run_info.get("script_hash"):
        script_verification = verify_file(
            run_info["script_path"],
            run_info["script_hash"],
            role="script",
            hash_cache=hash_cache,
        )
        file_verifications.append(script_verification)

    # A consumer of bytes produced by a FAILED run is resting on non-evidence
    # even when every hash still matches: treat it as an upstream failure.
    # Parents are the hash-bound producers from the shared lineage resolver.
    if propagate and not upstream_failed:
        from ._routes import _session_bindings

        bindings, _ = _session_bindings(db, session_id)
        upstream_failed = any(
            run_failed(db.get_run(b.parent))
            for b in bindings
            if b.file_path in input_hashes
        )

    # Determine overall status.
    #
    # A run whose recorded execution FAILED is never verified: its files are
    # not evidence, whatever their hashes say. This outranks every
    # hash-derived state.
    #
    # Order matters: a *local* failure (MISMATCH on an output/script, or a
    # MISSING output) is always more severe than upstream propagation —
    # the local failure says "this run's own artifacts are wrong now",
    # which the user must fix regardless of chain state. We check those
    # first. Only when every locally-checkable file passes do we fall back
    # to the upstream-only signal — that becomes SUSPECT (or MISMATCH if
    # the caller opted into the legacy 2-state collapse).
    locally_failed_files = [
        f for f in file_verifications if f.role != "input" and not f.is_verified
    ]
    if run_failed(run_info):
        status = VerificationStatus.FAILED
    elif locally_failed_files:
        # Pick MISMATCH if any local artifact mismatches; MISSING only when
        # every local failure is "file absent" (matches the original
        # severity preference).
        if any(f.status == VerificationStatus.MISMATCH for f in locally_failed_files):
            status = VerificationStatus.MISMATCH
        elif all(f.status == VerificationStatus.MISSING for f in locally_failed_files):
            status = VerificationStatus.MISSING
        else:
            status = VerificationStatus.UNKNOWN
    elif upstream_failed:
        # Every local file (output / script) verifies cleanly; only the
        # upstream chain is broken. This is the SUSPECT case — surface it
        # so the DAG view can render it in its own colour ("upstream-
        # failed-but-locally-valid"). The collapse_suspect knob folds it
        # back into MISMATCH for callers that still want the legacy
        # 2-state behaviour.
        status = (
            VerificationStatus.MISMATCH
            if collapse_suspect
            else VerificationStatus.SUSPECT
        )
    elif all(f.is_verified for f in file_verifications):
        status = VerificationStatus.VERIFIED
    elif any(f.status == VerificationStatus.MISMATCH for f in file_verifications):
        status = VerificationStatus.MISMATCH
    elif any(f.status == VerificationStatus.MISSING for f in file_verifications):
        status = VerificationStatus.MISSING
    else:
        status = VerificationStatus.UNKNOWN

    return RunVerification(
        session_id=session_id,
        script_path=run_info.get("script_path"),
        status=status,
        files=file_verifications,
        combined_hash_expected=run_info.get("combined_hash"),
        combined_hash_current=None,
        provenance=run_info.get("provenance", "tracked") or "tracked",
        exception_reason=run_info.get("exception_reason"),
    )


# EOF
