#!/usr/bin/env python3
"""Whether clew has a store scope for a project — answered without minting one."""

from __future__ import annotations

import os
from pathlib import Path

from .._db._scope import PROJECT_SCOPE_ENV, _read_project_id, project_id_path


def project_scope_exists(root: Path) -> bool:
    """True when ``root`` has a persisted clew project id, or the env pins one.

    The same two sources :func:`scitex_clew._db._scope.resolve_project_scope`
    reads for an explicit root, minus its last resort (minting a new id),
    which would write into the project.
    """
    if (os.environ.get(PROJECT_SCOPE_ENV) or "").strip():
        return True
    return _read_project_id(project_id_path(Path(root))) is not None


# EOF
