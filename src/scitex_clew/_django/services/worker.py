"""One request per process, authenticated tenant, explicit project scope.

This adapter checks all twenty physical Clew tables before reading rows.
Unsupported package schemas fail closed and require compatibility tests.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from uuid import UUID


class OutsideProject(Exception):
    pass


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        result = {field.name: getattr(value, field.name) for field in fields(value)}
        for name in ("is_verified", "is_verified_from_scratch"):
            if hasattr(value, name):
                result[name] = getattr(value, name)
        return result
    raise TypeError(type(value).__name__)


def execute(payload: dict):
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        from scitex_clew._django._optional import gui_dependency_error

        gui_dependency_error(exc)
    from scitex_dev.store import TenantScope, inspect_tenant_store

    os.environ["SCITEX_STORE_DSN"] = payload["dsn"]
    os.environ["SCITEX_CLEW_PROJECT"] = payload["project_scope"]
    root = Path(payload["root"]).resolve()
    os.chdir(root)
    from scitex_clew._claim._store import _CLAIMS_SCHEMA
    from scitex_clew._db._schema import (
        FILE_HASHES_SCHEMA,
        RUNS_SCHEMA,
        SESSION_PARENTS_SCHEMA,
        VERIFICATION_RESULTS_SCHEMA,
    )

    scope = TenantScope(UUID(payload["tenant_id"]))
    with psycopg.connect(payload["dsn"]) as connection:
        for schema in (
            RUNS_SCHEMA,
            FILE_HASHES_SCHEMA,
            VERIFICATION_RESULTS_SCHEMA,
            SESSION_PARENTS_SCHEMA,
            _CLAIMS_SCHEMA,
        ):
            status = inspect_tenant_store(
                connection, schema, scope, owner_role=payload["owner_role"]
            )
            if not status.ready:
                raise RuntimeError("Tenant catalogue check failed")

    import scitex_clew as clew
    from scitex_clew._db import get_db

    operation, parameters = payload["operation"], payload["parameters"]
    db = get_db()
    try:
        if operation == "runs":
            runs = db.list_runs(**parameters)
            return {
                "runs": runs,
                "count": len(runs),
                "limit": parameters["limit"],
                "offset": parameters["offset"],
            }
        if operation == "stats":
            return {
                **db.stats(),
                "db_found": True,
                "db_path": None,
                "backend": "postgresql",
            }
        if operation == "claims":
            claims = clew.list_claims(**parameters)
            return {
                "claims": [claim.to_dict() for claim in claims],
                "count": len(claims),
            }

        def checked(path):
            if path and not (root / path).resolve().is_relative_to(root):
                raise OutsideProject

        for row in db._file_hashes.rows():
            checked(row.values.get("file_path"))
        for row in db._runs.rows():
            checked(row.values.get("script_path"))
        for claim in clew.list_claims(limit=1_000_000, include_superseded=True):
            checked(claim.file_path)
            checked(claim.source_file)
        if operation == "status":
            return clew.status()
        if operation == "run":
            if db.get_run(parameters["session_id"]) is None:
                return {
                    "session_id": parameters["session_id"],
                    "status": "unknown",
                    "is_verified": False,
                    "files": [],
                }
            return clew.run(parameters["session_id"], from_scratch=False)
        if operation == "chain":
            return clew.chain(parameters["target"])
        if operation == "dag_json":
            from scitex_clew._viz._json import generate_dag_json

            return generate_dag_json(**parameters)
        if operation == "mermaid":
            return {"mermaid": clew.generate_mermaid_dag(**parameters)}
        raise ValueError("Unsupported read operation")
    finally:
        db.close()


def main() -> int:
    output = sys.stdout
    try:
        payload = json.load(sys.stdin)
        with redirect_stdout(sys.stderr):
            data = execute(payload)
        result, code = {"success": True, "data": data}, 0
    except OutsideProject:
        result, code = {"success": False, "code": "outside_project"}, 1
    except Exception:  # noqa: BLE001 — sanitize errors at the HTTP/process boundary
        result, code = {"success": False, "code": "store_unavailable"}, 1
    json.dump(result, output, default=_json_default)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
