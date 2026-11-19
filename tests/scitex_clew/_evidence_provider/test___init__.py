"""The package surface: the vendored contract schema and the entry point.

The schema is the version-pinned copy of scitex-live-paper's
``evidence-report.schema.json``; scitex-live-paper itself is never imported.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import jsonschema
from scitex_clew._evidence_provider import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    EvidenceEntry,
    load_schema,
)


def test_vendored_schema_is_a_valid_draft_2020_12_schema():
    # Arrange
    schema = load_schema()
    # Act
    meta = jsonschema.Draft202012Validator(jsonschema.Draft202012Validator.META_SCHEMA)
    errors = [e.message for e in meta.iter_errors(schema)]
    # Assert
    assert errors == []


def test_vendored_schema_is_the_pinned_contract_version():
    # Arrange
    schema = load_schema()
    # Act
    pinned = (schema["properties"]["schema"]["const"], schema["$id"])
    # Assert
    assert pinned == (
        SCHEMA_ID,
        f"https://scitex.ai/schemas/scitex-live-paper/evidence-report/{SCHEMA_VERSION}",
    )


def test_entry_point_is_discoverable_on_the_evidence_port():
    # Arrange
    group = entry_points(group="scitex.livepaper.renderers")
    # Act
    found = [(ep.load().port, ep.load().name) for ep in group if ep.name == "clew"]
    # Assert
    assert found == [("evidence", "clew")]


def test_entry_point_adapter_implements_the_port():
    # Arrange
    adapter = EvidenceEntry.adapter
    # Act
    methods = [
        callable(getattr(adapter, m, None))
        for m in ("evidence_report", "evidence_graph")
    ]
    # Assert
    assert methods == [True, True]
