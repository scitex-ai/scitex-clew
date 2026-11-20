"""The shipped exchange-format schemas are valid draft 2020-12 with pinned ids."""

from __future__ import annotations

import jsonschema
import pytest
from scitex_clew._exchange import BUNDLE_SCHEMA_ID, RERUN_SCHEMA_ID, load_schema


@pytest.mark.parametrize(
    ("name", "schema_id"),
    [
        ("evidence-bundle", BUNDLE_SCHEMA_ID),
        ("rerun-report", RERUN_SCHEMA_ID),
        ("rerun-report-1.0.0", "https://scitex.ai/schemas/scitex-clew/rerun-report/1.0.0"),
    ],
)
def test_schema_has_its_pinned_id(name, schema_id):
    # Arrange
    schema = load_schema(name)
    # Act
    got = schema["$id"]
    # Assert
    assert got == schema_id


@pytest.mark.parametrize("name", ["evidence-bundle", "rerun-report", "rerun-report-1.0.0"])
def test_schema_is_valid_draft_2020_12(name):
    # Arrange
    schema = load_schema(name)
    # Act
    errors = list(
        jsonschema.Draft202012Validator(
            jsonschema.Draft202012Validator.META_SCHEMA
        ).iter_errors(schema)
    )
    # Assert
    assert errors == []


def test_ids_are_the_published_urls():
    # Arrange
    ids = (BUNDLE_SCHEMA_ID, RERUN_SCHEMA_ID)
    # Act
    got = ids
    # Assert
    assert got == (
        "https://scitex.ai/schemas/scitex-clew/evidence-bundle/1.0.0",
        "https://scitex.ai/schemas/scitex-clew/rerun-report/1.1.0",
    )


# EOF
