#!/usr/bin/env python3
"""Database subpackage: SQLite-backed verification storage.

Re-exports the public surface that previously lived in `_db.py` so that
`from scitex_clew._db import VerificationDB, get_db, set_db` continues to
work after the cluster was reorganized into this subpackage.
"""

from ._chain import ChainMixin
from ._core import (
    VerificationDB,
    get_active_db_path,
    get_db,
    resolve_db_path,
    set_db,
    use_db,
)
from ._parents import ParentsMixin
from ._queries import VerificationQueryMixin

__all__ = [
    "VerificationDB",
    "get_active_db_path",
    "get_db",
    "resolve_db_path",
    "set_db",
    "use_db",
    "ChainMixin",
    "ParentsMixin",
    "VerificationQueryMixin",
]

# EOF
