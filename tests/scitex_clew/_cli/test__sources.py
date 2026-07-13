#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`clew register-source --from-list <file>` compiles a path list into the JSON.

Real temp DB + files (no mocks): a human-editable list (with # comments + blank
lines) of source paths registers into the signable JSON manifest in one call.

Also covers `clew grounding <claim-location> [--workdir] [--json]` — the CLI
wrapper around `scitex_clew.is_claim_grounded` (scitex-todo card
`clew-per-claim-grounding-api`).
"""

import json
import os

from click.testing import CliRunner

from scitex_clew._cli._main import main
from scitex_clew._cli._sources import register_source_cmd
from scitex_clew._claim._register import add_claim
from scitex_clew._db import set_db, use_db


def test_from_list_registers_listed_paths(tmp_path):
    # Arrange
    db = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
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
    db = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
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
    db = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
    db.parent.mkdir(parents=True)
    # Act
    with use_db(db):
        result = CliRunner().invoke(register_source_cmd, [])
    # Assert
    assert result.exit_code != 0 and "no sources given" in result.output


class TestGroundingCli:
    def _set_clew_env(self, db_path):
        """Manually set + return the previous env values (no-mocks: this
        repo forbids the ``monkeypatch`` fixture — restore happens via
        ``self._restore_clew_env`` in a ``finally`` block)."""
        prev_db = os.environ.get("SCITEX_CLEW_DB_PATH")
        prev_auto = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
        os.environ["SCITEX_CLEW_DB_PATH"] = str(db_path)
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
        return prev_db, prev_auto

    def _restore_clew_env(self, prev_db, prev_auto):
        if prev_db is None:
            os.environ.pop("SCITEX_CLEW_DB_PATH", None)
        else:
            os.environ["SCITEX_CLEW_DB_PATH"] = prev_db
        if prev_auto is None:
            os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
        else:
            os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev_auto

    def test_grounded_claim_reports_grounded_json(self, tmp_path):
        # Arrange — is_claim_grounded resolves its OWN DB via
        # SCITEX_CLEW_DB_PATH (not the CLI's global use_db()), so it must be
        # set explicitly to match the seeded claim's store.
        db_path = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
        prev_env = self._set_clew_env(db_path)
        try:
            set_db(db_path)
            src = tmp_path / "raw.csv"
            src.write_text("x\n")
            manifest_path = tmp_path / ".scitex" / "clew" / "signed" / "sources.json"
            from scitex_clew._sources import register_source

            register_source([str(src)], sources_path=str(manifest_path))
            paper = tmp_path / "p.tex"
            paper.write_text("v\n")
            claim = add_claim(
                file_path=str(paper),
                claim_type="value",
                line_number=1,
                claim_value="1",
                source_file=str(src),
            )
            runner = CliRunner()
            # Act
            result = runner.invoke(
                main,
                ["grounding", claim.claim_id, "--workdir", str(tmp_path), "--json"],
            )
            # Assert
            payload = json.loads(result.output)
            assert (
                result.exit_code == 0
                and payload["grounded"] is True
                and payload["reason"] == "grounded"
            )
        finally:
            self._restore_clew_env(*prev_env)

    def test_unknown_claim_reports_claim_not_found_human_output(self, tmp_path):
        # Arrange
        db_path = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
        prev_env = self._set_clew_env(db_path)
        try:
            runner = CliRunner()
            # Act
            result = runner.invoke(
                main, ["grounding", "nope_claim", "--workdir", str(tmp_path)]
            )
            # Assert
            assert result.exit_code == 0 and "NOT GROUNDED" in result.output
        finally:
            self._restore_clew_env(*prev_env)
