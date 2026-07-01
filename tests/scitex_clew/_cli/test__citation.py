#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``clew verify-citations`` + ``clew citation list``.

Mirrors ``src/scitex_clew/_cli/_citation.py``. The compiler (scitex-writer)
gates the build on this command's exit code.

Per PA-306 §3 (no mocks): real isolated DB via set_db + CliRunner + a real
temp .bib file. Per PA-307 §3: AAA marker comments + one observable assertion
per test.
"""

from __future__ import annotations

import json

import pytest

CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli import _exit_codes as codes
from scitex_clew._cli._main import main
from scitex_clew._db import set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    set_db(tmp_path / "cli_citation.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    return CliRunner()


_BIB = """
@article{Berens2009,
  author = {Berens, Philipp},
  title = {CircStat},
  journal = {J Stat Soft},
  doi = {10.18637/jss.v031.i10}
}
@article{Pinto2023,
  author = {Pinto, X},
  title = {Hallucinated},
  note = {Auto-generated stub}
}
"""


def test_verified_bib_key_exits_zero(runner, tmp_path):
    # Arrange — scholar pushed Berens as a real source; bib matches.
    import scitex_clew as clew

    clew.add_citation("Berens2009", doi="10.18637/jss.v031.i10")
    bib = tmp_path / "refs.bib"
    bib.write_text(_BIB)
    # Act
    result = runner.invoke(
        main, ["verify-citations", "--bib", str(bib), "--keys", "Berens2009"]
    )
    # Assert
    assert result.exit_code == codes.OK


def test_stub_bib_key_exits_citation_stub(runner, tmp_path):
    # Arrange — Pinto is an auto-generated stub in the bib, never resolved.
    bib = tmp_path / "refs.bib"
    bib.write_text(_BIB)
    # Act
    result = runner.invoke(
        main, ["verify-citations", "--bib", str(bib), "--keys", "Pinto2023"]
    )
    # Assert
    assert result.exit_code == codes.CITATION_STUB


def test_json_format_emits_per_key_map(runner, tmp_path):
    # Arrange
    bib = tmp_path / "refs.bib"
    bib.write_text(_BIB)
    # Act
    result = runner.invoke(
        main,
        ["verify-citations", "--bib", str(bib), "--keys", "Pinto2023", "--format", "json"],
    )
    # Assert
    assert json.loads(result.output)["citations"]["Pinto2023"]["status"] == "stub"


def test_missing_bib_errors(runner, tmp_path):
    # Arrange / Act — nonexistent bib path.
    result = runner.invoke(main, ["verify-citations", "--bib", str(tmp_path / "no.bib")])
    # Assert
    assert result.exit_code != 0


# EOF
