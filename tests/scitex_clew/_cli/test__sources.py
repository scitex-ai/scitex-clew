#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`clew register-source --from-list <file>` compiles a path list into the JSON.

Real store + files (no mocks): a human-editable list (with # comments + blank
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


def test_from_list_registers_listed_paths(tmp_path):
    # Arrange
    a = tmp_path / "a.csv"
    a.write_text("x\n1\n")
    b = tmp_path / "b.csv"
    b.write_text("y\n2\n")
    listfile = tmp_path / "CLEW_SOURCE_LIST.txt"
    listfile.write_text(f"# my sources\n{a}\n\n{b}\n")
    manifest = tmp_path / "signed" / "sources.json"
    # Act
    result = CliRunner().invoke(
        register_source_cmd,
        ["--from-list", str(listfile), "--sources-path", str(manifest)],
    )
    # Assert — both listed paths compiled into the JSON manifest.
    body = manifest.read_text() if manifest.exists() else result.output
    assert "a.csv" in body and "b.csv" in body


def test_from_list_missing_path_fails_loud(tmp_path):
    # Arrange — a list naming a nonexistent file.
    listfile = tmp_path / "CLEW_SOURCE_LIST.txt"
    listfile.write_text(f"{tmp_path / 'nope.csv'}\n")
    # Act
    result = CliRunner().invoke(register_source_cmd, ["--from-list", str(listfile)])
    # Assert
    assert result.exit_code != 0 and "not found" in result.output


def test_no_files_and_no_list_fails_loud(tmp_path):
    # Arrange
    # Act
    result = CliRunner().invoke(register_source_cmd, [])
    # Assert
    assert result.exit_code != 0 and "no sources given" in result.output


class TestGroundingCli:
    def _set_clew_env(self):
        """Manually set + return the previous env value (no-mocks: this
        repo forbids the ``monkeypatch`` fixture — restore happens via
        ``self._restore_clew_env`` in a ``finally`` block).

        There is no store to select here. clew has no database file, and
        ``is_claim_grounded`` reads THE store this host uses; test isolation
        is the autouse ``isolated_store`` fixture in tests/conftest.py, which
        gives every test its own throwaway PostgreSQL schema. Only the
        auto-export switch still needs setting.
        """
        prev_auto = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
        return prev_auto

    def _restore_clew_env(self, prev_auto):
        if prev_auto is None:
            os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
        else:
            os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev_auto

    def test_grounded_claim_reports_grounded_json(self, tmp_path):
        # Arrange — the claim is seeded into this test's own store, which is
        # also the store `clew grounding` reads. `--workdir` still selects
        # the per-capsule sources manifest.
        prev_env = self._set_clew_env()
        try:
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
            self._restore_clew_env(prev_env)

    def test_unknown_claim_reports_claim_not_found_human_output(self, tmp_path):
        # Arrange
        prev_env = self._set_clew_env()
        try:
            runner = CliRunner()
            # Act
            result = runner.invoke(
                main, ["grounding", "nope_claim", "--workdir", str(tmp_path)]
            )
            # Assert
            assert result.exit_code == 0 and "NOT GROUNDED" in result.output
        finally:
            self._restore_clew_env(prev_env)
