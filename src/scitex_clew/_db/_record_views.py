#!/usr/bin/env python3
"""Views over ONE session's decoded file rows — the read side of ``file_hashes``.

Every per-session read (``get_file_hashes``, ``get_frozen_files``,
``get_external_files``, ``get_file_records``) is a view of the same rows. They
used to be four separate scans of the whole table; a ``verify`` touched each
run with five of them, so its cost grew as (runs in the slice) x (rows in the
project). Now one query fetches a session's rows
(:meth:`~scitex_clew._db._file_hashes.FileHashMixin.session_file_records`) and
every view below derives from that list.

:class:`RecordViewsMixin` is shared by :class:`~scitex_clew._db._core.VerificationDB`
and by the per-pass read cache of ``verify``
(:class:`scitex_clew._chain._pass_cache.PassRecords`), so a cached view and an
uncached one cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["RECORD_KEYS", "RecordViewsMixin", "decode_record"]

#: Keys of a public :meth:`RecordViewsMixin.get_file_records` entry.
RECORD_KEYS = (
    "file_path",
    "hash",
    "recorded_at",
    "role",
    "derived_from",
    "external",
    "size_bytes",
)


def decode_record(values: Mapping[str, Any]) -> dict[str, Any]:
    """One ``file_hashes`` row as a dict: JSON columns parsed, ``frozen`` kept."""
    raw = values.get("derived_from")
    ext = values.get("external")
    return {
        "file_path": values.get("file_path"),
        "hash": values.get("hash"),
        "recorded_at": values.get("recorded_at"),
        "role": values.get("role"),
        "derived_from": json.loads(raw) if raw else None,
        "external": json.loads(ext) if ext else None,
        "size_bytes": values.get("size_bytes"),
        "frozen": bool(values.get("frozen")),
    }


def _of_role(records, role: str | None):
    return [r for r in records if role is None or r["role"] == role]


class RecordViewsMixin:
    """Per-session views; requires ``session_file_records(session_id)``."""

    def get_file_hashes(
        self, session_id: str, role: str | None = None
    ) -> dict[str, str]:
        """``{file_path: hash}`` of a session's rows (optionally one role)."""
        return {
            r["file_path"]: r["hash"]
            for r in _of_role(self.session_file_records(session_id), role)
        }

    def get_frozen_files(self, session_id: str, role: str | None = None) -> set:
        """File paths whose ``frozen`` flag is set for a session.

        Additive helper — does not change the return type of
        ``get_file_hashes`` so all existing callers remain behavior-identical.
        """
        return {
            r["file_path"]
            for r in _of_role(self.session_file_records(session_id), role)
            if r["frozen"]
        }

    def get_file_records(
        self, session_id: str, role: str | None = None
    ) -> list[dict[str, Any]]:
        """Return a session's file rows WITH their record time.

        Like :meth:`get_file_hashes` but keeps ``recorded_at``, which the
        lineage resolver needs to bind an input to a producer that recorded
        the same bytes BEFORE the input was loaded.

        Returns
        -------
        list of dict
            ``[{"file_path", "hash", "recorded_at", "role", "derived_from",
            "external", "size_bytes"}, ...]`` in record order. ``derived_from``
            is the declared list (see ``add_file_hash``) or ``None`` when
            undeclared; ``external`` is the outside-the-project payload or
            ``None`` for an in-project file.
        """
        return [
            {key: r[key] for key in RECORD_KEYS}
            for r in _of_role(self.session_file_records(session_id), role)
        ]

    def get_external_files(
        self, session_id: str, role: str | None = "input"
    ) -> dict[str, dict]:
        """``{path: external payload}`` of a session's files read from OUTSIDE
        the project root (see ``add_file_hash``)."""
        return {
            r["file_path"]: r["external"]
            for r in _of_role(self.session_file_records(session_id), role)
            if r["external"]
        }


# EOF
