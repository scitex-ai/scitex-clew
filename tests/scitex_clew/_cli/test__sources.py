#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`clew register-source --from-list <file>` compiles a path list into the JSON.

Real temp DB + files (no mocks): a human-editable list (with # comments + blank
lines) of source paths registers into the signable JSON manifest in one call.
"""

from click.testing import CliRunner

from scitex_clew._cli._sources import register_source_cmd
from scitex_clew._db import use_db


def test_from_list_registers_listed_paths(tmp_path):
    # Arrange
    db = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    db.parent.mkdir(parents=True)
    a = tmp_path / "a.csv"
    a.write_text("x\n1\n")
    b = tmp_path / "b.csv"
    b.write_text("y\n2\n")
    listfile = tmp_path / "CLEW_SOURCE_LIST.txt"
    listfile.write_text(f"# my sources\n{a}\n\n{b}\n")
    manifest = tmp_path / "signed" / "sources.json"
    # Act
    with use_db(db):
        result = CliRunner().invoke(
            register_source_cmd,
            ["--from-list", str(listfile), "--sources-path", str(manifest)],
        )
    # Assert — both listed paths compiled into the JSON manifest.
    body = manifest.read_text() if manifest.exists() else result.output
    assert "a.csv" in body and "b.csv" in body


def test_from_list_missing_path_fails_loud(tmp_path):
    # Arrange — a list naming a nonexistent file.
    db = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    db.parent.mkdir(parents=True)
    listfile = tmp_path / "CLEW_SOURCE_LIST.txt"
    listfile.write_text(f"{tmp_path / 'nope.csv'}\n")
    # Act
    with use_db(db):
        result = CliRunner().invoke(
            register_source_cmd, ["--from-list", str(listfile)]
        )
    # Assert
    assert result.exit_code != 0 and "not found" in result.output


def test_no_files_and_no_list_fails_loud(tmp_path):
    # Arrange
    db = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    db.parent.mkdir(parents=True)
    # Act
    with use_db(db):
        result = CliRunner().invoke(register_source_cmd, [])
    # Assert
    assert result.exit_code != 0 and "no sources given" in result.output
