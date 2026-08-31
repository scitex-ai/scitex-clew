#!/usr/bin/env python3
# Timestamp: "2026-08-29 (clew-postgres-store-migration)"
# File: src/scitex_clew/_attest/_stamp.py
"""External hash timestamping for temporal integrity.

Provides independent temporal proof that a verification chain was consistent
at a specific point in time. Only hashes are transmitted — never actual data.

Backends (increasing trust level):
  - file:    Local JSON file with timestamp (development/testing)
  - rfc3161: RFC 3161 Timestamping Authority (production standard)
  - zenodo:  Zenodo deposit with DOI (archival, citable)

This module drives ``scitex_dev.store.Store`` on the target
:func:`host_store` resolves — THE store this host uses (ADR-0006) — for its
own ``stamps`` table (sole owner, no cross-table joins). It also READS the
``runs`` Store (``VerificationDB._runs``) to compute the root hash — no
writes. This module constructs no DSN and no path of its own; the one
switch is ``SCITEX_STORE_DSN``, read by ``host_store()``.

Store has no WHERE/ORDER-BY/LIMIT: every query below is
``store.rows()`` (or ``store.get(key)`` for exact lookups) plus a Python
filter/sort — an accepted O(n)-scan trade-off for what is normally a small
per-project DB, matching the rest of this migration.

``stamps.metadata`` is kept as ``FieldKind.TEXT`` (pre-serialized JSON via
``json.dumps``/``json.loads``), not ``FieldKind.JSON`` — mirrors the
deliberate choice made for ``runs.metadata`` in PR #143: existing callers
(``check_stamp``, ``list_stamps``) read/parse it as raw JSON text, and
changing the stored type would be an observable behavior change for no
benefit.

There is no reliable business timestamp to sort "most recent stamp" by
that is guaranteed monotonic with insertion order (the old autoincrement
``id`` served that role pre-migration). Per this migration's established
rule, ``check_stamp``/``list_stamps`` sort by ``row.hlc``
(``wall_us``, ``logical``, ``node``) instead.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from scitex_dev.store import (
    ANY_REVISION,
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    WriterPolicy,
    host_store,
)

from .._db._scope import ProjectScopedStore

from .._db import get_db
from .._db._schema import resolve_node_id

STAMP_BACKENDS = ("file", "rfc3161", "zenodo", "scitex_cloud")


def _identity_field() -> FieldPolicy:
    return FieldPolicy(
        kind=FieldKind.TEXT,
        role=FieldRole.IDENTITY,
        required=True,
        merge=MergeRule.IMMUTABLE,
        indexed=False,
    )


def _data_field(
    kind: FieldKind,
    *,
    required: bool = False,
    merge: MergeRule = MergeRule.LAST_WRITER_WINS,
    indexed: bool = False,
) -> FieldPolicy:
    return FieldPolicy(kind=kind, role=FieldRole.DATA, required=required, merge=merge, indexed=indexed)


#: stamp_id is the sole IDENTITY field — it is already globally unique
#: (sha256 of root_hash + microsecond-resolution timestamp, truncated).
#: root_hash/timestamp/backend are NOT NULL in the original DDL; the rest
#: (service_url, response_token, run_count, metadata) stay nullable, matching
#: the original schema exactly. root_hash keeps its index (original
#: `idx_stamps_hash`).
STAMPS_SCHEMA = Schema.build(
    "stamps",
    {
        "project": _identity_field(),
        "stamp_id": _identity_field(),
        "root_hash": _data_field(FieldKind.TEXT, required=True, indexed=True),
        "timestamp": _data_field(FieldKind.TEXT, required=True),
        "backend": _data_field(FieldKind.TEXT, required=True),
        "service_url": _data_field(FieldKind.TEXT),
        "response_token": _data_field(FieldKind.TEXT),
        "run_count": _data_field(FieldKind.INTEGER),
        "metadata": _data_field(FieldKind.TEXT),
    },
)


@dataclass
class Stamp:
    """A temporal proof record."""

    stamp_id: str
    root_hash: str
    timestamp: str
    backend: str
    service_url: Optional[str]
    response_token: Optional[str]
    run_count: int
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "stamp_id": self.stamp_id,
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
            "backend": self.backend,
            "service_url": self.service_url,
            "response_token": self.response_token,
            "run_count": self.run_count,
            "metadata": self.metadata,
        }


def _stamps_store() -> Store:
    """Construct the ``stamps`` Store on the host store.

    Idempotent — Store.__init__ runs CREATE TABLE IF NOT EXISTS (+ additive
    migrations) under the dialect's schema lock, so this is safe to call
    repeatedly, matching the pre-migration ``migrate_add_stamps_table``
    contract. Each call opens its own connection; the underlying connection
    is reclaimed when the Store is garbage-collected.
    """
    target = host_store(pkg="scitex_clew", name="stamps")
    return ProjectScopedStore(
        Store(
            target,
            STAMPS_SCHEMA,
            node=resolve_node_id(),
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
    )


def migrate_add_stamps_table() -> None:
    """Create the stamps store's backing tables if not present. Safe to call multiple times."""
    _stamps_store()


def _ensure_stamps_table(db=None) -> Store:
    """Ensure the stamps Store exists, returning it.

    ``db`` is accepted and ignored: there is one store per host and it does
    not depend on which ``VerificationDB`` the caller happens to hold.
    """
    return _stamps_store()


def compute_root_hash(session_ids: Optional[List[str]] = None) -> Dict:
    """Compute a Merkle-like root hash over all (or selected) runs.

    The root hash combines all run combined_hashes in deterministic order,
    providing a single fingerprint for the entire verification state.

    Parameters
    ----------
    session_ids : list of str, optional
        Specific sessions to include. If None, includes all successful runs.

    Returns
    -------
    dict
        {root_hash, run_count, session_ids}
    """
    db = get_db()
    all_rows = db._runs.rows()

    if session_ids:
        wanted = set(session_ids)
        selected = [r for r in all_rows if r.values.get("session_id") in wanted]
    else:
        selected = [
            r
            for r in all_rows
            if r.values.get("status") == "success" and r.values.get("combined_hash") is not None
        ]
    selected.sort(key=lambda r: r.values.get("session_id") or "")

    if not selected:
        return {"root_hash": None, "run_count": 0, "session_ids": []}

    hasher = hashlib.sha256()
    ids = []
    for row in selected:
        session_id = row.values.get("session_id")
        combined_hash = row.values.get("combined_hash")
        hasher.update(session_id.encode())
        hasher.update((combined_hash or "").encode())
        ids.append(session_id)

    return {
        "root_hash": hasher.hexdigest(),
        "run_count": len(ids),
        "session_ids": ids,
    }


def stamp(
    backend: str = "file",
    service_url: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Stamp:
    """Record root hash with external timestamp.

    Parameters
    ----------
    backend : str
        One of: file, rfc3161, zenodo.
    service_url : str, optional
        URL for RFC 3161 TSA or Zenodo API.
    session_ids : list of str, optional
        Specific sessions to stamp. If None, stamps all successful runs.
    output_dir : str, optional
        Directory for file-based stamps (default: <db_dir>/stamps, i.e. .scitex/clew/runtime/stamps/).

    Returns
    -------
    Stamp
        The timestamp proof record.
    """
    if backend not in STAMP_BACKENDS:
        raise ValueError(
            f"Invalid backend '{backend}'. Must be one of: {STAMP_BACKENDS}"
        )

    root = compute_root_hash(session_ids)
    if not root["root_hash"]:
        raise ValueError("No runs to stamp (no successful runs with combined hashes)")

    now = datetime.now(timezone.utc).isoformat()
    root_hash = root["root_hash"]
    raw = f"{root_hash}:{now}"
    stamp_id = f"stamp_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    if backend == "file":
        result = _stamp_file(stamp_id, root, now, output_dir)
    elif backend == "rfc3161":
        result = _stamp_rfc3161(stamp_id, root, now, service_url)
    elif backend == "zenodo":
        result = _stamp_zenodo(stamp_id, root, now, service_url)
    elif backend == "scitex_cloud":
        result = _stamp_scitex_cloud(stamp_id, root, now, service_url)
    else:
        raise ValueError(f"Unsupported backend: {backend}")

    stamp_obj = Stamp(
        stamp_id=stamp_id,
        root_hash=root["root_hash"],
        timestamp=now,
        backend=backend,
        service_url=result.get("service_url"),
        response_token=result.get("response_token"),
        run_count=root["run_count"],
        metadata={"session_ids": root["session_ids"]},
    )

    # Store in database
    db = get_db()
    store = _ensure_stamps_table(db)
    store.put(
        {
            "stamp_id": stamp_obj.stamp_id,
            "root_hash": stamp_obj.root_hash,
            "timestamp": stamp_obj.timestamp,
            "backend": stamp_obj.backend,
            "service_url": stamp_obj.service_url,
            "response_token": stamp_obj.response_token,
            "run_count": stamp_obj.run_count,
            "metadata": json.dumps(stamp_obj.metadata),
        },
        expected_revision=ANY_REVISION,
    )

    return stamp_obj


def _stamp_from_row(row) -> Stamp:
    """Build a Stamp dataclass from a stamps-Store Row."""
    values = row.values
    metadata = values.get("metadata")
    return Stamp(
        stamp_id=values["stamp_id"],
        root_hash=values.get("root_hash"),
        timestamp=values.get("timestamp"),
        backend=values.get("backend"),
        service_url=values.get("service_url"),
        response_token=values.get("response_token"),
        run_count=values.get("run_count"),
        metadata=json.loads(metadata) if metadata else None,
    )


def _hlc_sort_key(row):
    """Insertion-order proxy: (wall_us, logical, node) is a total order."""
    return (row.hlc.wall_us, row.hlc.logical, row.hlc.node)


def check_stamp(stamp_id: Optional[str] = None) -> Dict:
    """Verify a stamp against current verification state.

    Parameters
    ----------
    stamp_id : str, optional
        Specific stamp to check. If None, checks the latest stamp.

    Returns
    -------
    dict
        {stamp, current_root_hash, matches, details}
    """
    db = get_db()
    store = _ensure_stamps_table(db)

    if stamp_id:
        row = store.get((stamp_id,))
    else:
        rows = store.rows()
        row = max(rows, key=_hlc_sort_key, default=None)

    if row is None:
        return {"status": "not_found", "message": "No stamps found"}

    stored_stamp = _stamp_from_row(row)

    # Recompute root hash from the same sessions
    session_ids = (
        stored_stamp.metadata.get("session_ids") if stored_stamp.metadata else None
    )
    current = compute_root_hash(session_ids)

    matches = current["root_hash"] == stored_stamp.root_hash
    details = []

    if matches:
        details.append(f"Root hash matches stamp from {stored_stamp.timestamp}")
    else:
        details.append(f"Root hash CHANGED since stamp at {stored_stamp.timestamp}")
        details.append(f"  Stamped:  {stored_stamp.root_hash[:32]}...")
        details.append(f"  Current:  {current['root_hash'][:32]}...")

    if current["run_count"] != stored_stamp.run_count:
        details.append(
            f"  Run count changed: {stored_stamp.run_count} → {current['run_count']}"
        )

    return {
        "stamp": stored_stamp.to_dict(),
        "current_root_hash": current["root_hash"],
        "matches": matches,
        "details": details,
    }


def list_stamps(limit: int = 20) -> List[Stamp]:
    """List all stamps."""
    db = get_db()
    store = _ensure_stamps_table(db)

    rows = store.rows()
    rows.sort(key=_hlc_sort_key, reverse=True)
    return [_stamp_from_row(row) for row in rows[:limit]]


# ── Backend implementations ──


def _stamp_file(stamp_id, root, timestamp, output_dir=None):
    """File-based stamping: write JSON proof to local directory."""
    if output_dir:
        stamp_dir = Path(output_dir)
    else:
        # Was ``db.db_path.parent / "stamps"``. There is no database file to
        # sit beside any more, so the JSON proofs land in the project's
        # regenerable-output directory — the same place claims.json goes.
        from .._db._core import _find_project_root

        stamp_dir = _find_project_root() / ".scitex" / "clew" / "runtime" / "stamps"

    stamp_dir.mkdir(parents=True, exist_ok=True)
    stamp_path = stamp_dir / f"{stamp_id}.json"

    proof = {
        "stamp_id": stamp_id,
        "root_hash": root["root_hash"],
        "timestamp": timestamp,
        "run_count": root["run_count"],
        "backend": "file",
    }

    stamp_path.write_text(json.dumps(proof, indent=2))
    return {"service_url": str(stamp_path), "response_token": None}


def _stamp_rfc3161(stamp_id, root, timestamp, service_url=None):
    """RFC 3161 Timestamping Authority."""
    try:
        import rfc3161ng
    except ImportError:
        raise ImportError(
            "RFC 3161 stamping requires 'rfc3161ng' package. "
            "Install with: pip install rfc3161ng"
        )

    url = service_url or "http://zeitstempel.dfn.de"
    certificate = rfc3161ng.RemoteTimestamper(url)

    hash_bytes = bytes.fromhex(root["root_hash"])
    tst = certificate.timestamp(data=hash_bytes)

    token_hex = tst.hex() if isinstance(tst, bytes) else str(tst)
    return {"service_url": url, "response_token": token_hex[:256]}


def _stamp_zenodo(stamp_id, root, timestamp, service_url=None):
    """Zenodo deposit: create a record with the root hash."""
    raise NotImplementedError(
        "Zenodo stamping is planned for a future release. "
        "Use 'file' or 'rfc3161' backend instead."
    )


def _stamp_scitex_cloud(stamp_id, root, timestamp, service_url=None):
    """SciTeX Cloud registry: register root hash with server-side timestamp."""
    from ._registry import get_registry

    registry = get_registry(base_url=service_url)
    result = registry.register(
        root["root_hash"],
        source_type="stamp",
        metadata={
            "stamp_id": stamp_id,
            "run_count": root["run_count"],
            "timestamp": timestamp,
        },
    )

    url = service_url or registry.base_url
    token = (
        result.get("data", {}).get("registered_at") if result.get("success") else None
    )
    return {"service_url": url, "response_token": token}


__all__ = [
    "STAMP_BACKENDS",
    "Stamp",
    "check_stamp",
    "compute_root_hash",
    "list_stamps",
    "migrate_add_stamps_table",
    "stamp",
]

# EOF
