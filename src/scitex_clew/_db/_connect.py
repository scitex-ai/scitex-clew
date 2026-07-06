#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stdlib-only SQLite connection helper for clew (zero-dependency).

clew is a ZERO-DEPENDENCY provenance recorder, so it cannot import
``scitex-db`` (which pulls numpy + pandas + scitex-core) to reuse its
connection tuning. Instead this module MIRRORS scitex-db's proven
connect configuration directly, using nothing but the standard library.

The mirrored values come from scitex-db's
``_sqlite3/_SQLite3Mixins/_ConnectionMixin.py:100-102``:

    PRAGMA journal_mode = WAL         # writable opens only
    PRAGMA synchronous  = NORMAL      # writable opens only
    PRAGMA busy_timeout = 300000      # 5 minutes; always

Why this matters: clew's provenance DBs are written by many concurrent
processes. Bare ``sqlite3.connect(path)`` has NO busy timeout, so a
second writer hits "database is locked" *immediately* instead of
retrying. ``busy_timeout`` is the core fix — it makes SQLite retry a
locked DB for up to 5 minutes, and it works on every filesystem. WAL
additionally lets readers and a writer proceed concurrently, but WAL
requires write access and does not stick on some networked/read-only
filesystems, so it is applied BEST-EFFORT for writable opens and
skipped for read-only opens.

This helper only opens the connection and applies the PRAGMAs; it does
NOT set ``row_factory`` or change ``isolation_level``. Each call site
keeps its own ``conn.row_factory = sqlite3.Row`` (where it had one) and
its existing commit/transaction semantics unchanged.
"""

from __future__ import annotations

import sqlite3


def connect(
    db_path,
    *,
    read_only: bool = False,
    timeout: float = 60.0,
) -> sqlite3.Connection:
    """Open an SQLite connection with clew's mirrored PRAGMA tuning.

    Parameters
    ----------
    db_path : str or os.PathLike
        Path to the SQLite database file. Opened with stdlib
        ``sqlite3.connect`` (read-write, creating the file if missing),
        preserving clew's existing open semantics.
    read_only : bool, default False
        When True, skip the WAL / synchronous PRAGMAs (they require and
        assume write access). ``busy_timeout`` is still applied so a
        concurrent writer holding a lock does not make the read fail
        instantly.
    timeout : float, default 60.0
        Passed to ``sqlite3.connect``: seconds the sqlite driver waits
        on a locked DB before raising. Mirrors scitex-db's 60.0 default.
        This is complementary to ``busy_timeout`` (the C-level retry).

    Returns
    -------
    sqlite3.Connection
        The open connection. ``row_factory`` / ``isolation_level`` are
        left at their defaults for the caller to set as before.
    """
    conn = sqlite3.connect(str(db_path), timeout=timeout)

    # Core fix: always retry a locked DB rather than failing instantly.
    # Works on every filesystem, read-only or writable.
    conn.execute("PRAGMA busy_timeout = 300000")  # 5 minutes

    if not read_only:
        # WAL requires write access and does not stick on some
        # networked / read-only filesystems. Apply best-effort so a
        # failure here never crashes the connect; busy_timeout above
        # still applies. Mirrors scitex-db's rw-only-WAL logic.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error:
            pass

    return conn


# EOF
