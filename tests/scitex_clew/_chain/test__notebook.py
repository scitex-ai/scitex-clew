#!/usr/bin/env python3
"""Notebook code identity, scheme-aware re-hashing and the rerun recipe.

The code hash is a CROSS-PACKAGE contract: scitex-session records it as
``entry["code_sha256"]`` and clew re-computes it to verify. The conformance
vector below is duplicated verbatim in scitex-session's
``tests/scitex_session/_lifecycle/test__notebook.py``. Change both or neither.
"""

from __future__ import annotations

import json

from scitex_clew._hash import hash_code, hash_file, hash_like
from scitex_clew._chain._notebook import (
    NOTEBOOK_CODE_PREFIX,
    hash_notebook_code,
    notebook_code_digest,
    rerun_recipe,
)

#: ipynb-code-v1 conformance vector (shared with scitex-session).
VECTOR_NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {},
    "cells": [
        {"cell_type": "code", "source": "a = 1\r\nb = 2", "metadata": {},
         "outputs": [], "execution_count": None},
        {"cell_type": "markdown", "source": "# x", "metadata": {}},
        {"cell_type": "code", "source": ["print(a)\n", 'print("é")'], "metadata": {},
         "outputs": [{"output_type": "stream", "name": "stdout", "text": "1"}],
         "execution_count": 7},
    ],
}  # fmt: skip
VECTOR_SHA256 = "cf7e2cc7afc91f1334d8d14aad99644cda863f2173227baed69996d2140a5d3d"


def _write(tmp_path, nb, name="v.ipynb"):
    path = tmp_path / name
    path.write_text(json.dumps(nb), encoding="utf-8")
    return path


def test_code_digest_matches_the_shared_conformance_vector(tmp_path):
    # Arrange
    path = _write(tmp_path, VECTOR_NOTEBOOK)
    # Act
    digest = notebook_code_digest(path)
    # Assert
    assert digest == VECTOR_SHA256


def test_stored_code_hash_carries_its_scheme_prefix(tmp_path):
    # Arrange
    path = _write(tmp_path, VECTOR_NOTEBOOK)
    # Act
    stored = hash_notebook_code(path)
    # Assert
    assert stored == NOTEBOOK_CODE_PREFIX + VECTOR_SHA256


def test_hash_code_of_a_notebook_is_its_code_hash(tmp_path):
    # Arrange
    path = _write(tmp_path, VECTOR_NOTEBOOK)
    # Act
    value = hash_code(path)
    # Assert
    assert value == NOTEBOOK_CODE_PREFIX + VECTOR_SHA256


def test_hash_code_of_a_script_is_its_byte_hash(tmp_path):
    # Arrange
    path = tmp_path / "s.py"
    path.write_text("print(1)\n")
    # Act
    value = hash_code(path)
    # Assert
    assert value == hash_file(path)


def test_hash_like_rehashes_a_notebook_recorded_as_data_by_bytes(tmp_path):
    # Arrange: an .ipynb recorded with a plain byte hash (an output / data)
    path = _write(tmp_path, VECTOR_NOTEBOOK)
    recorded = hash_file(path)
    # Act
    current = hash_like(path, recorded)
    # Assert
    assert current == recorded


def test_hash_like_ignores_new_outputs_for_a_code_hash(tmp_path):
    # Arrange
    path = _write(tmp_path, VECTOR_NOTEBOOK)
    recorded = hash_notebook_code(path)
    nb = json.loads(json.dumps(VECTOR_NOTEBOOK))
    nb["cells"][0]["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "x"}
    ]
    _write(tmp_path, nb)
    # Act
    current = hash_like(path, recorded)
    # Assert
    assert current == recorded


def test_rerun_recipe_runs_the_notebook_from_the_recorded_cwd():
    # Arrange
    run = {
        "script_path": "/p/notebooks/a.ipynb",
        "metadata": json.dumps({
            "cwd": "/p/notebooks",
            "python": {"executable": "/venv/bin/python"},
            "entry": {"kind": "notebook", "path": "/p/notebooks/a.ipynb",
                      "invocation": "cell", "executed_in_order": True},
        }),
    }  # fmt: skip
    # Act
    recipe = rerun_recipe(run)
    # Assert
    assert recipe["command"] == [
        "/venv/bin/python", "-m", "scitex_clew", "execute-notebook",
        "/p/notebooks/a.ipynb", "--cwd", "/p/notebooks",
    ]  # fmt: skip


def test_rerun_recipe_is_none_for_a_script_run():
    # Arrange
    run = {
        "script_path": "/p/s.py",
        "metadata": json.dumps({"entry": {"kind": "script"}}),
    }
    # Act
    recipe = rerun_recipe(run)
    # Assert
    assert recipe is None
