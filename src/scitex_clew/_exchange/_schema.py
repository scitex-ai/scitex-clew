#!/usr/bin/env python3
"""The exchange-format JSON Schemas (draft 2020-12), shipped in the wheel.

* ``evidence-bundle.schema.1.0.0.json`` —
  ``$id`` https://scitex.ai/schemas/scitex-clew/evidence-bundle/1.0.0
* ``rerun-report.schema.1.0.0.json`` —
  ``$id`` https://scitex.ai/schemas/scitex-clew/rerun-report/1.0.0

Validation needs ``jsonschema`` (the ``[sign]`` extra installs it with
``cryptography``); clew core stays stdlib-only, so it is imported lazily and
its absence fails loudly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "BUNDLE_SCHEMA_ID",
    "BUNDLE_SCHEMA_PATH",
    "RERUN_SCHEMA_ID",
    "RERUN_SCHEMA_PATH",
    "SchemaValidatorMissing",
    "load_schema",
    "schema_errors",
]

_HERE = Path(__file__).resolve().parent
BUNDLE_SCHEMA_PATH = _HERE / "evidence-bundle.schema.1.0.0.json"
RERUN_SCHEMA_PATH = _HERE / "rerun-report.schema.1.0.0.json"
BUNDLE_SCHEMA_ID = "https://scitex.ai/schemas/scitex-clew/evidence-bundle/1.0.0"
RERUN_SCHEMA_ID = "https://scitex.ai/schemas/scitex-clew/rerun-report/1.0.0"

_PATHS = {"evidence-bundle": BUNDLE_SCHEMA_PATH, "rerun-report": RERUN_SCHEMA_PATH}

VALIDATOR_HINT = (
    "validating an evidence bundle needs the 'jsonschema' package: install it "
    "with `pip install 'scitex-clew[sign]'`."
)


class SchemaValidatorMissing(RuntimeError):
    """``jsonschema`` is not installed."""


def load_schema(name: str = "evidence-bundle") -> dict:
    """The shipped schema ``evidence-bundle`` or ``rerun-report``."""
    return json.loads(_PATHS[name].read_text(encoding="utf-8"))


def schema_errors(document: Any, name: str = "evidence-bundle") -> list[str]:
    """Every violation of schema ``name`` by ``document`` (``[]`` = valid)."""
    try:
        import jsonschema
    except ImportError as exc:
        raise SchemaValidatorMissing(VALIDATOR_HINT) from exc
    validator = jsonschema.Draft202012Validator(load_schema(name))
    return sorted(
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(document)
    )


# EOF
