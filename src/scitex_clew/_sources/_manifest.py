#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered-source manifest — host-side, hash-pinned trust whitelist.

Why this exists
---------------
``green = link-hash-consistency`` is not enough: a claim can be
link-hash-consistent yet reach NO true source (its provenance chain
terminates at a hand-made leaf). This module loads a human-registered
whitelist of *trusted source files*, each pinned by ``sha256``, so the
verify/export gate can demote an otherwise-green-but-ungrounded claim to
the ``unsourced`` verdict.

Manifest format (JSON)::

    {
      "schema": "sources-1.0",
      "sources": [{"path": "<relpath>", "sha256": "<hex>"}],
      "signature": null
    }

* ``path`` is relative to the project root (the ``.scitex/`` parent).
* ``sha256`` is the full 64-char hex digest of the file at registration
  time (the flat per-file v0.2 contract locked with scitex-dataset — NOT
  the nested ``digest{algo,value,of}`` capsule digest).
* ``signature`` is RESERVED (default ``null``): accepted-but-not-enforced
  in this release. The signing follow-on gpg-signs the manifest against a
  committed public key and rejects an unsigned/badly-signed manifest. A
  pluggable no-op verify seam (:func:`verify_signature`) is provided now so
  that follow-on is a pure additive enforcement change.

Resolution tiers (mirrors :func:`scitex_clew._db._core.resolve_db_path`):
tier1 explicit arg > tier2 ``$SCITEX_CLEW_SOURCES`` > tier3
``<project_root>/.scitex/clew/sources.json``.

This manifest is READ by verify/export; it is NEVER written by verify or
any agent-facing code path. The only sanctioned writer is the
``clew register-source`` CLI (human-run) — see :mod:`._writer`.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple, Union

from .._core import getLogger
from .._db._core import _find_project_root

_log = getLogger(__name__)

SOURCES_SCHEMA = "sources-1.0"


def full_sha256(path: Union[str, Path]) -> str:
    """Return the full 64-char sha256 hex digest of ``path`` (streamed)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class SourceEntry:
    """One registered source: a hash-pinned trusted file.

    ``valid`` is the tamper-check outcome — ``True`` iff the file exists on
    disk AND its current sha256 equals the pinned value. An invalid entry is
    NOT a trust anchor and is surfaced loudly (``reason`` says why).
    """

    path: str  # relpath as stored in the manifest
    sha256: str  # pinned full hex digest
    abspath: Path  # resolved absolute path (root / path)
    valid: bool
    reason: str  # "OK" | "MISSING" | "TAMPERED"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "abspath": str(self.abspath),
            "valid": self.valid,
            "reason": self.reason,
        }


@dataclass
class SourcesManifest:
    """A loaded, tamper-checked registered-source manifest.

    ``active`` is the OPT-IN switch: the gate only fires when at least one
    VALID entry is present. An absent manifest loads as ``None`` (see
    :func:`load_sources_manifest`); a present-but-empty or all-invalid
    manifest is ``active is False`` so the gate stays dormant.
    """

    schema: str
    root: Path
    path: Path
    entries: List[SourceEntry] = field(default_factory=list)
    signature: Optional[Any] = None
    # Signature enforcement (set by load_sources_manifest). ``signing_enforced``
    # is True iff a ``signed/signing.pub`` is committed for this project; when
    # enforced, ``signature_valid`` is the Ed25519 verification result. When NOT
    # enforced (no committed pubkey) ``signature_valid`` is None and the manifest
    # is trusted as before (opt-in — zero behavior change until a key is added).
    signing_enforced: bool = False
    signature_valid: Optional[bool] = None

    @property
    def valid_entries(self) -> List[SourceEntry]:
        return [e for e in self.entries if e.valid]

    @property
    def invalid_entries(self) -> List[SourceEntry]:
        return [e for e in self.entries if not e.valid]

    @property
    def trusted(self) -> bool:
        """False iff signing is ENFORCED but the manifest's signature is
        missing/invalid — an untrusted manifest anchors NOTHING (so a tampered
        or unsigned-under-an-enforcing-key manifest cannot ground any claim:
        "without the key it can't be run/edited")."""
        return not (self.signing_enforced and not self.signature_valid)

    @property
    def active(self) -> bool:
        """Gate FIRES iff signing is enforced (a committed signing.pub) OR >=1
        VALID anchor exists.

        When signing is enforced the gate fires even for an UNTRUSTED manifest —
        so is_grounded blocks ALL its claims (an unsigned or tampered manifest
        must not silently pass by making the gate go dormant)."""
        if self.signing_enforced:
            return True
        return bool(self.valid_entries)

    def anchor_paths(self) -> Set[str]:
        """Resolved absolute paths of the VALID anchors (for grounding); EMPTY
        when the manifest is untrusted (unsigned/tampered under an enforcing key)."""
        if not self.trusted:
            return set()
        return {str(e.abspath) for e in self.valid_entries}

    def pinned_for(self, abspath: str) -> Optional[str]:
        """Pinned sha256 for a VALID anchor at ``abspath`` (else ``None``);
        always ``None`` when the manifest is untrusted."""
        if not self.trusted:
            return None
        for e in self.valid_entries:
            if str(e.abspath) == abspath:
                return e.sha256
        return None


def _project_root_for(sources_path: Path) -> Path:
    """Project root a manifest's relpaths resolve against.

    The canonical layout is ``<root>/.scitex/clew/sources.json`` — when the
    manifest sits there, the root is unambiguous (three parents up). For a
    manifest resolved from an explicit/env path elsewhere, fall back to the
    cwd-based project-root walk (same as the DB resolver).
    """
    p = sources_path.resolve()
    if p.parent.name == "clew" and p.parent.parent.name == ".scitex":
        return p.parent.parent.parent
    return _find_project_root()


def resolve_sources_path(
    sources_path: Optional[Union[str, Path]] = None,
) -> Tuple[Path, str]:
    """Resolve the manifest path via the three-tier precedence.

    Mirrors :func:`scitex_clew._db._core.resolve_db_path` exactly:
    tier1 explicit arg > tier2 ``$SCITEX_CLEW_SOURCES`` > tier3
    ``<project_root>/.scitex/clew/sources.json``.

    Returns
    -------
    tuple of (Path, str)
        The resolved path and a human-readable label of the producing tier.
        This function only resolves — it neither creates nor requires the
        file.
    """
    if sources_path is not None:
        return Path(sources_path), "explicit sources_path argument"
    env_path = os.environ.get("SCITEX_CLEW_SOURCES")
    if env_path:
        return Path(env_path), "SCITEX_CLEW_SOURCES environment variable"
    # tier3: prefer the canonical signable location signed/sources.json, then
    # user_definitions/ (pre-rename), then the flat legacy path (see
    # _resolve_sources_tier3).
    return _resolve_sources_tier3(_find_project_root() / ".scitex" / "clew")


def _resolve_sources_tier3(clew_dir: Path) -> Tuple[Path, str]:
    """Tier-3 manifest precedence within a ``.scitex/clew`` dir.

    signed/sources.json > user_definitions/sources.json (pre-rename) > flat
    legacy sources.json. If none exists yet, default NEW manifests to signed/ so
    register-source + sign + the gate all share one canonical location. Split
    out (taking ``clew_dir`` explicitly) so it is exercisable against a real temp
    dir without patching the project-root walk.
    """
    signed = clew_dir / "signed" / "sources.json"
    for candidate, label in (
        (signed, "signed/ manifest (project-root walk)"),
        (
            clew_dir / "user_definitions" / "sources.json",
            "user_definitions/ manifest (pre-rename, project-root walk)",
        ),
        (clew_dir / "sources.json", "legacy .scitex/clew/sources.json"),
    ):
        if candidate.exists():
            return candidate, label
    return signed, "signed/ default (project-root walk; not yet created)"


def verify_signature(raw: dict, signature: Optional[str]) -> bool:
    """Pluggable signature-verify seam — a NO-OP in this release.

    Reserved for the signing follow-on: it will gpg-verify the manifest
    against a committed public key and reject an unsigned/bad manifest. In
    this release signing is not enforced, so this always returns ``True``.
    Keeping the seam here means the follow-on is a pure additive change.
    """
    return True


def _check_manifest_signature(
    raw: dict, root: Path
) -> Tuple[bool, Optional[bool]]:
    """Determine signature-enforcement state for a manifest.

    Enforcement is OPT-IN: it activates only when a public key is committed at
    ``<root>/.scitex/clew/signed/signing.pub``. Returns
    ``(signing_enforced, signature_valid)``:

    * no committed pubkey -> ``(False, None)`` — signing NOT enforced (zero
      behavior change; the manifest stays trusted as before).
    * pubkey present -> ``(True, <Ed25519 verify result>)`` — the manifest must
      carry a valid signature over its canonical form, else it is untrusted and
      anchors nothing.

    Fails CLOSED: if a pubkey is committed but verification is unavailable
    (python-cryptography / the ``[all]`` extra not installed here), returns
    ``(True, False)`` — an unverifiable manifest is untrusted, so signing cannot
    be bypassed by dropping the crypto dependency.
    """
    pubkey_path = root / ".scitex" / "clew" / "signed" / "signing.pub"
    if not pubkey_path.exists():
        return False, None

    try:
        from ._signing import is_signed, verify_manifest

        valid = verify_manifest(raw, pubkey_path.read_bytes())
    except RuntimeError as exc:  # pragma: no cover - only when [all] is absent
        _log.warning(
            "clew: signing.pub is committed at %s but signature verification is "
            "unavailable (%s) — the manifest is treated as UNTRUSTED. Install "
            "scitex-clew[all] in this environment to verify signed sources.",
            pubkey_path,
            exc,
        )
        return True, False

    if not valid:
        why = (
            "is UNSIGNED"
            if not is_signed(raw)
            else "has an INVALID signature (tampered or wrong key)"
        )
        _log.warning(
            "clew: manifest %s under an enforcing signing.pub (%s) — its anchors "
            "are UNTRUSTED and every claim will be unsourced until it is re-signed "
            "with `clew sign`.",
            why,
            pubkey_path,
        )
    return True, bool(valid)


def load_sources_manifest(
    sources_path: Optional[Union[str, Path]] = None,
    *,
    root: Optional[Union[str, Path]] = None,
) -> Optional[SourcesManifest]:
    """Load + tamper-check the registered-source manifest.

    Parameters
    ----------
    sources_path : str or Path, optional
        Explicit manifest path (tier 1). Falls through to
        ``$SCITEX_CLEW_SOURCES`` (tier 2) then the tier-3 default.
    root : str or Path, optional
        Project root the manifest relpaths resolve against. When ``None``,
        derived from the manifest location (canonical layout) or the cwd
        project-root walk.

    Returns
    -------
    SourcesManifest or None
        ``None`` when the manifest file does not exist — the gate is then
        INACTIVE (opt-in: zero behavior change). A present manifest is parsed,
        schema-validated, and every entry tamper-checked (recompute each
        file's sha256 vs the pinned value).

    Raises
    ------
    ValueError
        On a malformed manifest (not JSON, wrong schema string, missing
        ``sources`` list, or a malformed entry). Fail-loud, never silent-empty.
    """
    resolved, _tier = resolve_sources_path(sources_path)
    resolved = Path(resolved)
    if not resolved.exists():
        return None  # opt-in: no manifest => gate inactive

    try:
        raw = json.loads(resolved.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"Registered-source manifest is malformed (not valid JSON): "
            f"{resolved} — {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"Registered-source manifest must be a JSON object: {resolved}"
        )
    schema = raw.get("schema")
    if schema != SOURCES_SCHEMA:
        raise ValueError(
            f"Registered-source manifest has unexpected schema {schema!r} "
            f"(expected {SOURCES_SCHEMA!r}): {resolved}"
        )
    sources = raw.get("sources")
    if not isinstance(sources, list):
        raise ValueError(
            f"Registered-source manifest 'sources' must be a list: {resolved}"
        )

    signature = raw.get("signature")

    root_path = Path(root) if root is not None else _project_root_for(resolved)

    entries: List[SourceEntry] = []
    for i, item in enumerate(sources):
        if not isinstance(item, dict) or "path" not in item or "sha256" not in item:
            raise ValueError(
                f"Registered-source manifest entry #{i} is malformed "
                f"(need 'path' and 'sha256'): {item!r} in {resolved}"
            )
        rel = str(item["path"])
        pinned = str(item["sha256"]).lower()
        abspath = (root_path / rel).resolve()
        if not abspath.exists():
            valid, reason = False, "MISSING"
        else:
            current = full_sha256(abspath).lower()
            if current == pinned:
                valid, reason = True, "OK"
            else:
                valid, reason = False, "TAMPERED"
        entries.append(
            SourceEntry(
                path=rel,
                sha256=pinned,
                abspath=abspath,
                valid=valid,
                reason=reason,
            )
        )

    signing_enforced, signature_valid = _check_manifest_signature(raw, root_path)
    return SourcesManifest(
        schema=schema,
        root=root_path,
        path=resolved,
        entries=entries,
        signature=signature,
        signing_enforced=signing_enforced,
        signature_valid=signature_valid,
    )


# EOF
