#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WAL-safe auto-rename of a predecessor clew DB to the canonical name.

clew's default DB is ``<root>/.scitex/clew/runtime/clew.db`` (the
fleet-wide ``.scitex/<pkg>/runtime/<pkg>.db`` convention; ``.db`` is also
required for scitex-io interop). Older capsules used ``db.sqlite``. This
module transparently renames a predecessor to ``clew.db`` on first open.

The correctness-critical part is WAL safety: clew opens DBs in WAL mode
(see ``_connect.connect``), so a predecessor ``db.sqlite`` may carry an
uncheckpointed ``db.sqlite-wal`` (+ ``-shm``) sidecar holding
committed-but-not-yet-checkpointed rows. A naive ``os.rename`` of only
the main file would orphan (and lose) that data. So this checkpoints the
WAL back into the main file BEFORE the rename.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def wal_safe_rename(predecessor: Path, target: Path) -> None:
    """Rename ``predecessor`` → ``target`` without losing WAL-only data.

    Steps:

    1. Open the predecessor and run ``PRAGMA wal_checkpoint(TRUNCATE)`` —
       this folds the ``-wal`` back into the main file and empties it. If
       the predecessor is NOT in WAL mode, the checkpoint is a harmless
       no-op; any checkpoint failure is swallowed so it never aborts the
       rename of a non-WAL DB.
    2. Close the connection (releasing the ``-wal``/``-shm`` sidecars).
    3. ``os.replace`` the single main file → ``target`` (atomic; never
       leaves the DB half-renamed).
    4. Remove any leftover ``-wal``/``-shm`` sidecars of the predecessor
       so they cannot shadow ``target``'s fresh sidecars.

    A quiescent-DB checkpoint + metadata rename is instant even at
    multi-GB, so this is safe to run inline on first open.
    """
    predecessor = Path(predecessor)
    target = Path(target)

    # Fold any WAL-only data back into the main file, then release locks.
    try:
        conn = sqlite3.connect(str(predecessor))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        # Non-WAL DB (or checkpoint unsupported): the main file already
        # holds all data, so the rename below is still complete + safe.
        pass

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(predecessor, target)

    # Remove any stragglers so they don't shadow target's fresh sidecars.
    for suffix in ("-wal", "-shm"):
        sidecar = predecessor.with_name(predecessor.name + suffix)
        try:
            sidecar.unlink()
        except FileNotFoundError:
            pass


# EOF
