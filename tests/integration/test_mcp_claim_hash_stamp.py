#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 — MCP-tool tests for claim/hash/stamp wrappers."""

from __future__ import annotations

import asyncio
import json

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db


def _run(coro):
    return asyncio.run(coro)


def _get_tools(mcp):
    from scitex_clew._mcp import get_tools_sync

    tools = get_tools_sync(mcp)
    if isinstance(tools, dict):
        return tools
    return {t.name: t for t in tools}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db_path = tmp_path / "f1_mcp.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def mcp_with_all_tools():
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP

    from scitex_clew._mcp.tools import register_all_tools

    m = FastMCP(name="t-f1")
    register_all_tools(m)
    return m


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_clew_add_claim_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_add_claim" in _get_tools(mcp_with_all_tools)

    def test_clew_list_claims_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_list_claims" in _get_tools(mcp_with_all_tools)

    def test_clew_verify_claim_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_verify_claim" in _get_tools(mcp_with_all_tools)

    def test_clew_hash_file_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_hash_file" in _get_tools(mcp_with_all_tools)

    def test_clew_hash_directory_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_hash_directory" in _get_tools(mcp_with_all_tools)

    def test_clew_stamp_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_stamp" in _get_tools(mcp_with_all_tools)

    def test_clew_list_stamps_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_list_stamps" in _get_tools(mcp_with_all_tools)

    def test_clew_check_stamp_registered(self, mcp_with_all_tools):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "clew_check_stamp" in _get_tools(mcp_with_all_tools)


# ---------------------------------------------------------------------------
# clew_claim_*
# ---------------------------------------------------------------------------


class TestClaimTools:
    def test_claim_add_happy_parsed_claim_id_startswith_claim(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        fn = _get_tools(mcp_with_all_tools)["clew_add_claim"].fn
        out = _run(fn(file_path=str(manuscript), claim_type="statistic"))
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["claim_id"].startswith("claim_")

    def test_claim_add_happy_parsed_claim_type_statistic(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        fn = _get_tools(mcp_with_all_tools)["clew_add_claim"].fn
        out = _run(fn(file_path=str(manuscript), claim_type="statistic"))
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["claim_type"] == "statistic"


    def test_claim_add_error_on_invalid_type(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("x")
        fn = _get_tools(mcp_with_all_tools)["clew_add_claim"].fn
        out = _run(fn(file_path=str(manuscript), claim_type="bogus"))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert "error" in parsed

    def test_claim_list_empty(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_list_claims"].fn
        out = _run(fn())
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert parsed["count"] == 0

    def test_claim_verify_not_found(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_verify_claim"].fn
        out = _run(fn(claim_id_or_location="claim_doesnotexist"))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert parsed["status"] == "not_found"


# ---------------------------------------------------------------------------
# clew_hash_*
# ---------------------------------------------------------------------------


class TestHashTools:
    def test_hash_file_happy_parsed_path_str_f(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("hello")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_file"].fn
        out = _run(fn(path=str(f)))
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["path"] == str(f)

    def test_hash_file_happy_isinstance_parsed_hash_str_and_len_parsed_hash_0(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("hello")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_file"].fn
        out = _run(fn(path=str(f)))
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(parsed["hash"], str) and len(parsed["hash"]) > 0


    def test_hash_file_missing_returns_error(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_hash_file"].fn
        out = _run(fn(path=str(tmp_path / "nope.txt")))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert "error" in parsed

    def test_hash_directory_happy(self, mcp_with_all_tools, tmp_path):
        # Arrange
        # Arrange
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_directory"].fn
        out = _run(fn(path=str(tmp_path)))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert parsed["count"] >= 2

    def test_hash_directory_not_a_directory_returns_error(
        self, mcp_with_all_tools, tmp_path
    ):
        # Arrange
        # Arrange
        f = tmp_path / "file.txt"
        f.write_text("x")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_directory"].fn
        out = _run(fn(path=str(f)))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert "error" in parsed


# ---------------------------------------------------------------------------
# clew_stamp_*
# ---------------------------------------------------------------------------


class TestStampTools:
    def test_stamp_with_no_runs_returns_error(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_stamp"].fn
        out = _run(fn(backend="file"))
        # Act
        # Act
        parsed = json.loads(out)
        # Assert
        # Assert
        assert "error" in parsed

    def test_list_stamps_empty_parsed_count_0(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_list_stamps"].fn
        out = _run(fn())
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["count"] == 0

    def test_list_stamps_empty_parsed_stamps(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_list_stamps"].fn
        out = _run(fn())
        # Act
        # Act
        parsed = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["stamps"] == []


    def test_check_stamp_not_found(self, mcp_with_all_tools):
        # Arrange
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_check_stamp"].fn
        out = _run(fn(stamp_id="bogus_stamp"))
        # Act
        # Act
        parsed = json.loads(out)
        # Either 'not_found' or some error key
        # Assert
        # Assert
        assert parsed.get("status") == "not_found" or "error" in parsed


# EOF
