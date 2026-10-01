"""Leaf-owned Clew process isolation, backed by generic SDK capabilities."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from scitex_sdk.host import (
        AccessError as ClewRequestError,
    )
    from scitex_sdk.host import (
        CapabilityUnavailable as ClewUnavailable,
    )
    from scitex_sdk.host import (
        ProjectAccess,
        project_access,
        store_access,
    )
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)


def project_context(request) -> dict:
    project = project_access(request)
    store = store_access(request, project.id)
    return {
        "tenant_id": str(store.tenant_id),
        "dsn": store.dsn,
        "project_scope": store.project_scope,
        "root": str(project.root),
        "owner_role": store.owner_role,
    }


def project_path(root: str, value: str) -> str:
    return str(ProjectAccess("selected", "Selected project", Path(root)).path(value))


def execute(context: dict, operation: str, parameters: dict):
    """Separate process for Clew's environment, cwd and cached store state.

    Credentials use stdin. This is state isolation, not an OS file sandbox.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SCITEX_")
        and key
        not in {"COVERAGE_PROCESS_START", "COVERAGE_FILE", "DJANGO_SETTINGS_MODULE"}
    }
    source_root = Path(__file__).resolve().parents[3]
    environment["PYTHONPATH"] = str(source_root)
    try:
        completed = subprocess.run(
            [sys.executable, "-P", str(Path(__file__).with_name("worker.py"))],
            input=json.dumps(
                {**context, "operation": operation, "parameters": parameters}
            ),
            text=True,
            capture_output=True,
            cwd=context["root"],
            env=environment,
            timeout=30,
            check=False,
        )
        result = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ClewUnavailable("Private Clew store is unavailable") from exc
    if completed.returncode != 0 or not result.get("success"):
        if result.get("code") == "outside_project":
            raise ClewRequestError(
                "Recorded files need an explicit project-path migration", 422
            )
        raise ClewUnavailable(
            "Private Clew store failed its access or compatibility check"
        )
    return result["data"]
