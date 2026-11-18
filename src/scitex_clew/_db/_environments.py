#!/usr/bin/env python3
"""Package provenance stored once per environment, referenced from run rows.

WHY
---
scitex-session (>= 0.5.0) hands every run's metadata a ``package_provenance``
mapping: per imported distribution, its install source, wheel fingerprint and
the files edited since installation. For a scientific stack that is ~9 KB, and
it is the same for every session run in the same environment. Stored inline
in ``runs.metadata`` it was repeated in every run row AND in every oplog entry
that wrote the metadata (the opening put, each ``merge_run_metadata``) —
the bulk of a run's store footprint, carrying no new information after the
first run. scitex-session 0.6.0 made the same move for its run directories
(``.scitex/session/environments/<sha256>.json``).

WHAT
----
The ``environments`` store holds ONE row per distinct provenance set of a
project, keyed by the SHA-256 of its canonical JSON (sorted keys, no
whitespace, UTF-8 — the same scheme as scitex-session, so the key equals the
name of the session's environment file for the same set). A run row's
metadata keeps a reference instead of the set::

    "package_provenance_ref": {"format", "sha256", "distributions"}

Nothing is dropped: readers (:meth:`VerificationDB.get_run`,
:meth:`VerificationDB.list_runs`) put the set back as ``package_provenance``,
after checking its hash, so every consumer — slices, the
``ENV_NOT_REPRODUCIBLE`` check, ``run_environment`` — reads what it always
read. A run row written before this change (provenance inline) reads
unchanged; there is no data migration. The schema change is additive: a new
table set, nothing altered in the existing ones.

FAILURE MODES, never silent
---------------------------
* The environment row cannot be written: the provenance stays inline and
  ``package_provenance_store_error`` says why (the information is never lost
  to save space).
* A reference cannot be resolved (row missing, or its content does not match
  its hash): the run reads with NO ``package_provenance`` — which every
  consumer treats as "not recorded", never as "all fine" — plus
  ``package_provenance_unresolved`` naming the reason, and a warning.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from scitex_dev.store import ANY_REVISION

from .._core._logging import getLogger
from ._schema import ENVIRONMENTS_SCHEMA

logger = getLogger(__name__)

__all__ = [
    "PROVENANCE_KEY",
    "REF_FORMAT",
    "REF_KEY",
    "UNRESOLVED_KEY",
    "EnvironmentStoreMixin",
    "canonical_provenance_bytes",
]

PROVENANCE_KEY = "package_provenance"
REF_KEY = "package_provenance_ref"
STORE_ERROR_KEY = "package_provenance_store_error"
#: Read-time annotation only; never written to the store.
UNRESOLVED_KEY = "package_provenance_unresolved"
#: ``format`` of a reference written by clew.
REF_FORMAT = "scitex-clew/package-provenance/v1"


def canonical_provenance_bytes(provenance: Mapping[str, Any]) -> bytes:
    """Canonical JSON bytes of a provenance mapping (what is hashed).

    Identical to scitex-session's ``canonical_provenance_bytes``, so one
    provenance set has one hash in both places.
    """
    return json.dumps(
        provenance,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


class EnvironmentStoreMixin:
    """Write/resolve the per-environment provenance rows of :class:`VerificationDB`.

    Requires ``self._lazy_store(name, schema)`` and ``self._env_cache``
    (``{sha256: provenance}``; content-addressed, so never stale).
    """

    @property
    def _environments(self):
        return self._lazy_store("environments", ENVIRONMENTS_SCHEMA)

    # -- write ---------------------------------------------------------------

    def store_environment(self, provenance: Mapping[str, Any]) -> dict[str, Any]:
        """Store ``provenance`` once (idempotent) and return its reference."""
        data = canonical_provenance_bytes(provenance)
        digest = hashlib.sha256(data).hexdigest()
        memo = self._env_cache
        if digest not in memo:
            if self._environments.get((digest,)) is None:
                self._environments.put(
                    {
                        "sha256": digest,
                        "format": REF_FORMAT,
                        "distributions": len(provenance),
                        "provenance": data.decode("utf-8"),
                        "recorded_at": datetime.now().isoformat(),
                    },
                    expected_revision=ANY_REVISION,
                )
            memo[digest] = json.loads(data)
        return {
            "format": REF_FORMAT,
            "sha256": digest,
            "distributions": len(provenance),
        }

    def _externalize(self, meta: dict[str, Any]) -> dict[str, Any]:
        """``meta`` with an inline provenance set replaced by its reference."""
        out = {k: v for k, v in meta.items() if k != UNRESOLVED_KEY}
        provenance = out.get(PROVENANCE_KEY)
        if not isinstance(provenance, Mapping) or not provenance:
            return out
        try:
            ref = self.store_environment(provenance)
        except Exception as exc:  # noqa: BLE001 - recorded + warned, kept inline
            out[STORE_ERROR_KEY] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "scitex-clew: could not store the environment provenance (%s); "
                "it stays inline in this run's row",
                out[STORE_ERROR_KEY],
            )
            return out
        del out[PROVENANCE_KEY]
        out.pop(STORE_ERROR_KEY, None)
        out[REF_KEY] = ref
        return out

    def _metadata_json(
        self, metadata: Mapping[str, Any] | None, *, default=None
    ) -> str | None:
        """The JSON text a run row stores for ``metadata``.

        ``default`` is ``json.dumps``'s: None (the run-opening put) raises on
        a value JSON cannot hold, as it always did; a merge passes ``str``.
        """
        if not metadata:
            return None
        return json.dumps(self._externalize(dict(metadata)), default=default)

    # -- read ----------------------------------------------------------------

    def get_environment(self, sha256: str) -> dict | None:
        """The provenance set stored under ``sha256`` (hash-checked), or None.

        Raises ``ValueError`` when the stored content does not match the key.
        """
        memo = self._env_cache
        if sha256 in memo:
            return memo[sha256]
        row = self._environments.get((sha256,))
        if row is None:
            return None
        text = row.values.get("provenance") or ""
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != sha256:
            raise ValueError(f"environment row {sha256[:16]} does not match its hash")
        memo[sha256] = json.loads(text)
        return memo[sha256]

    def _resolve_ref(self, ref: Mapping[str, Any]) -> dict:
        digest = str(ref.get("sha256") or "")
        found = self.get_environment(digest) if digest else None
        if found is not None:
            return found
        # A scitex-session reference also names its environment file.
        path = ref.get("abspath")
        if path and Path(path).is_file():
            data = Path(path).read_bytes()
            if hashlib.sha256(data).hexdigest() == digest:
                return json.loads(data.decode("utf-8"))
            raise ValueError(f"environment file {path} does not match sha256 {digest}")
        raise LookupError(f"no environment row for sha256 {digest or '<missing>'}")

    def _resolve_metadata(self, raw: Any) -> Any:
        """Run-row metadata text with a provenance reference resolved inline."""
        if not isinstance(raw, str) or REF_KEY not in raw:
            return raw
        try:
            meta = json.loads(raw)
        except ValueError:
            return raw
        if not isinstance(meta, dict) or not isinstance(meta.get(REF_KEY), Mapping):
            return raw
        if isinstance(meta.get(PROVENANCE_KEY), Mapping):
            return raw
        try:
            meta[PROVENANCE_KEY] = self._resolve_ref(meta[REF_KEY])
        except Exception as exc:  # noqa: BLE001 - surfaced on the row + warned
            meta[UNRESOLVED_KEY] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "scitex-clew: package provenance of a run is unresolvable (%s); "
                "it reads as not recorded",
                meta[UNRESOLVED_KEY],
            )
        return json.dumps(meta, default=str)


# EOF
