"""Leaf-owned Clew process isolation, backed by generic SDK capabilities."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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
    runtime = os.environ.get("SCITEX_DIR")
    if not runtime or not Path(runtime).is_absolute():
        raise ClewUnavailable("An explicit Clew runtime directory is required")
    try:
        runtime_root = Path(runtime).resolve()
        workers = runtime_root / "clew" / "runtime" / "gui-workers"
        resolved_workers = workers.resolve()
    except (OSError, RuntimeError) as exc:
        raise ClewUnavailable("Clew runtime directory is unavailable") from exc
    if not resolved_workers.is_relative_to(runtime_root):
        raise ClewUnavailable("Clew runtime directory must stay inside its root")
    try:
        workers.mkdir(parents=True, exist_ok=True)
        source_root = Path(__file__).resolve().parents[3]
        with TemporaryDirectory(prefix="request-", dir=workers) as temporary:
            request_runtime = Path(temporary)
            environment = {
                key: os.environ[key]
                for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE")
                if key in os.environ
            }
            environment["PYTHONPATH"] = str(source_root)
            for key, directory in {
                "SCITEX_DIR": "scitex",
                "TMPDIR": "tmp",
                "XDG_CONFIG_HOME": "config",
                "XDG_CACHE_HOME": "cache",
                "XDG_DATA_HOME": "data",
                "XDG_STATE_HOME": "state",
                "XDG_RUNTIME_DIR": "run",
            }.items():
                location = request_runtime / directory
                location.mkdir()
                environment[key] = str(location)
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
                if not isinstance(result, dict) or type(result.get("success")) is not bool:
                    raise ClewUnavailable("Private Clew store returned an invalid response")
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
            if "data" not in result:
                raise ClewUnavailable("Private Clew store returned an invalid response")
            return result["data"]
    except OSError as exc:
        raise ClewUnavailable("Clew runtime directory is unavailable") from exc
