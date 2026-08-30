#!/usr/bin/env python3
# Timestamp: "2026-02-09 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_node_class.py
"""Semantic node classification for verification DAG nodes.

Five classes classify pipeline nodes by their role:
  - source:     Data acquisition scripts
  - input:      Raw data, configuration files
  - processing: Transform/analysis scripts
  - output:     Intermediate/final data products
  - claim:      Paper-level assertions (figures, statistics, text)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from scitex_dev.store import ANY_REVISION

from .._db._core import VerificationDB

# Canonical node classes
NODE_CLASSES = ("source", "input", "processing", "output", "claim")

# File extensions → inferred node_class
_SCRIPT_EXTS = {".py", ".sh", ".r", ".R", ".jl", ".m"}
_DATA_EXTS = {
    ".csv",
    ".tsv",
    ".npy",
    ".npz",
    ".hdf5",
    ".h5",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".pkl",
    ".pickle",
    ".parquet",
    ".feather",
}
_FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".tiff", ".eps"}
_TEX_EXTS = {".tex", ".bib", ".bbl"}


def infer_node_class(file_path: str, role: str) -> Optional[str]:
    """Infer node_class from file extension and session role.

    Parameters
    ----------
    file_path : str
        Path to the file.
    role : str
        Session role: 'input', 'output', or 'script'.

    Returns
    -------
    str or None
        Inferred node class, or None if ambiguous.
    """
    ext = Path(file_path).suffix.lower()

    if role == "script":
        return "source" if ext in _SCRIPT_EXTS else None

    if role == "input":
        if ext in _SCRIPT_EXTS:
            return "source"
        if ext in _DATA_EXTS:
            return "input"
        return "input"

    if role == "output":
        if ext in _DATA_EXTS:
            return "output"
        if ext in _FIGURE_EXTS:
            return "output"
        if ext in _TEX_EXTS:
            return "claim"
        return "output"

    return None


def migrate_add_node_class() -> None:
    """Ensure the ``file_hashes`` store has a ``node_class`` field.

    ``node_class`` is a plain (optional) field of ``FILE_HASHES_SCHEMA``
    (see ``_db/_schema.py``) — ``Store.__init__`` creates it as a real
    column the first time a ``file_hashes`` store is opened, so there is no
    separate ALTER-TABLE step left for this function to perform.

    This is now effectively a no-op kept for backward-compatible call
    sites that treat it as an idempotent "make sure the store is ready"
    step: constructing ``VerificationDB`` is enough to guarantee the field
    exists on a freshly created store.

    Note: ``scitex_dev.store``'s additive-migration mechanism only
    back-fills the store's OWN internal columns (the oplog/cursor fence),
    not arbitrary new user schema fields — so a ``file_hashes`` store table
    created before ``node_class`` existed in the schema will not
    retroactively gain the column. Worth knowing if a schema field is ever
    added to an already-deployed Store schema.
    """
    VerificationDB()


def set_node_class(
    session_id: str,
    file_path: str,
    node_class: str,
) -> None:
    """Set node_class for every file hash record matching (session_id, file_path).

    Parameters
    ----------
    session_id : str
        Session identifier.
    file_path : str
        Path to the file.
    node_class : str
        One of: source, input, processing, output, claim.

    Notes
    -----
    Matches on ``(session_id, file_path)`` only — NOT the full
    ``(session_id, file_path, role)`` composite identity — reproducing the
    original raw-SQL ``UPDATE ... WHERE session_id = ? AND file_path = ?``
    behavior. A file recorded under multiple roles in the same session
    (e.g. both an input to one step and the output of another) has every
    matching row updated.
    """
    if node_class not in NODE_CLASSES:
        raise ValueError(
            f"Invalid node_class '{node_class}'. Must be one of: {NODE_CLASSES}"
        )
    db = VerificationDB()
    matches = [
        row
        for row in db._file_hashes.rows()
        if row.values.get("session_id") == session_id
        and row.values.get("file_path") == file_path
    ]
    for row in matches:
        db._file_hashes.put(
            {
                "session_id": row.values["session_id"],
                "file_path": row.values["file_path"],
                "role": row.values["role"],
                "node_class": node_class,
            },
            expected_revision=ANY_REVISION,
        )


def auto_classify() -> int:
    """Auto-classify all file_hashes records missing node_class.

    Returns
    -------
    int
        Number of records updated.
    """
    db = VerificationDB()
    updated = 0
    for row in db._file_hashes.rows():
        if row.values.get("node_class") is not None:
            continue
        nc = infer_node_class(row.values.get("file_path"), row.values.get("role"))
        if nc:
            db._file_hashes.put(
                {
                    "session_id": row.values["session_id"],
                    "file_path": row.values["file_path"],
                    "role": row.values["role"],
                    "node_class": nc,
                },
                expected_revision=ANY_REVISION,
            )
            updated += 1
    return updated


__all__ = [
    "NODE_CLASSES",
    "infer_node_class",
    "migrate_add_node_class",
    "set_node_class",
    "auto_classify",
]
