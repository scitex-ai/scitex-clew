#!/usr/bin/env python3
"""The default runtime export marks its directory as never-committed state.

Real store, real files; no mocks.
"""

from __future__ import annotations

import warnings

import scitex_clew as clew


def _register(root):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clew.add_claim("paper.tex", "value", 1, "1", claim_id="x", project_root=root)


def test_default_export_writes_a_star_gitignore_in_runtime(tmp_path):
    # Arrange
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    _register(root)
    # Act
    with clew.project_root(root):
        out = clew.export_claims_json()
    # Assert
    ignore = out.parent / ".gitignore"
    assert (out.parent.name, ignore.read_text()) == ("runtime", "*\n")


def test_existing_runtime_gitignore_is_left_alone(tmp_path):
    # Arrange
    root = tmp_path / "proj"
    runtime = root / ".scitex" / "clew" / "runtime"
    runtime.mkdir(parents=True)
    (root / ".git").mkdir()
    (runtime / ".gitignore").write_text("claims.json\n")
    _register(root)
    # Act
    with clew.project_root(root):
        clew.export_claims_json()
    # Assert
    assert (runtime / ".gitignore").read_text() == "claims.json\n"


def test_explicit_export_path_gets_no_gitignore(tmp_path):
    # Arrange: a caller-chosen location is the caller's to manage
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    _register(root)
    target = tmp_path / "out" / "claims.json"
    # Act
    with clew.project_root(root):
        clew.export_claims_json(path=target)
    # Assert
    assert not (target.parent / ".gitignore").exists()


# EOF
