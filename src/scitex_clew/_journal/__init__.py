#!/usr/bin/env python3
"""Kill-durable recording: per-session journals and their recovery.

* :mod:`._file` — the append-only journal a session writes as it records.
* :mod:`._lifecycle` — opening it for a tracker, SIGTERM/SIGHUP, interpreter exit.
* :mod:`._recover` — replaying the journals of processes that died.

Only :mod:`._file` is imported here: the store layer imports this package,
and recovery imports the store layer.
"""

from ._file import (  # noqa: F401
    JOURNAL_DIR_ENV,
    JOURNAL_ENV,
    SessionJournal,
    journal_dir,
    journal_enabled,
    store_fingerprint,
)


def recover_journals(dry_run: bool = False) -> list[dict]:
    """Replay the journals of dead processes (see :mod:`._recover`)."""
    from ._recover import recover_journals as _recover

    return _recover(dry_run=dry_run)


# EOF
