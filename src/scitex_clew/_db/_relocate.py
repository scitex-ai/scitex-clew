#!/usr/bin/env python3
"""Re-key a session's recorded paths after its run directory moved.

A session manager may move its run directory at close (scitex-session >= 0.3.6
moves ``RUNNING/<ID>`` to ``FINISHED_*/<ID>`` and reports the move as
``relocations`` in the close-hook metadata). Recorded rows must then point at
the final paths, or ``verify`` reports every output of the run MISSING.
"""

from __future__ import annotations

import json
import os

from scitex_dev.store import ANY_REVISION

__all__ = ["RelocationMixin", "relocated"]

#: Every non-scope field of a ``file_hashes`` row (see ``_schema.py``).
_FILE_HASH_FIELDS = (
    "session_id",
    "file_path",
    "role",
    "hash",
    "size_bytes",
    "frozen",
    "host",
    "recorded_at",
    "node_class",
    "derived_from",
    "external",
)


def relocated(path: str | None, old: str, new: str) -> str | None:
    """``path`` moved from under ``old`` to under ``new`` (None if not under)."""
    if not path:
        return None
    old, new = old.rstrip(os.sep), new.rstrip(os.sep)
    if path == old:
        return new
    if path.startswith(old + os.sep):
        return new + path[len(old) :]
    return None


class RelocationMixin:
    """Requires ``self._file_hashes`` and ``self._rows_for_session``."""

    def relocate_session_paths(
        self,
        session_id: str,
        old_prefix: str,
        new_prefix: str,
    ) -> int:
        """Move a session's recorded paths from ``old_prefix`` to ``new_prefix``.

        Rows whose ``file_path`` is ``old_prefix`` or lies below it are
        re-keyed to the same relative path under ``new_prefix`` (every other
        field kept; the old row is hidden — a Store never deletes). Declared
        ``derived_from`` entries of the session are rewritten the same way.
        Returns the number of rows changed.
        """
        changed = 0
        with self._file_hashes.batch():
            for row in self._rows_for_session(session_id, None):
                values = row.values
                path = values.get("file_path")
                raw = values.get("derived_from")
                declared = json.loads(raw) if raw else None
                new_declared = (
                    [relocated(p, old_prefix, new_prefix) or p for p in declared]
                    if declared is not None
                    else None
                )
                new_path = relocated(path, old_prefix, new_prefix)
                if new_path is None and new_declared == declared:
                    continue
                payload = {f: values.get(f) for f in _FILE_HASH_FIELDS}
                payload["file_path"] = new_path or path
                payload["derived_from"] = (
                    json.dumps(new_declared) if new_declared is not None else None
                )
                self._file_hashes.put(payload, expected_revision=ANY_REVISION)
                if new_path is not None:
                    self._file_hashes.hide(
                        (session_id, path, values.get("role")),
                        expected_revision=ANY_REVISION,
                    )
                changed += 1
        return changed


# EOF
