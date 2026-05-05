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
    def test_clew_claim_add_registered(self, mcp_with_all_tools):
        assert "clew_claim_add" in _get_tools(mcp_with_all_tools)

    def test_clew_claim_list_registered(self, mcp_with_all_tools):
        assert "clew_claim_list" in _get_tools(mcp_with_all_tools)

    def test_clew_claim_verify_registered(self, mcp_with_all_tools):
        assert "clew_claim_verify" in _get_tools(mcp_with_all_tools)

    def test_clew_hash_file_registered(self, mcp_with_all_tools):
        assert "clew_hash_file" in _get_tools(mcp_with_all_tools)

    def test_clew_hash_directory_registered(self, mcp_with_all_tools):
        assert "clew_hash_directory" in _get_tools(mcp_with_all_tools)

    def test_clew_stamp_registered(self, mcp_with_all_tools):
        assert "clew_stamp" in _get_tools(mcp_with_all_tools)

    def test_clew_list_stamps_registered(self, mcp_with_all_tools):
        assert "clew_list_stamps" in _get_tools(mcp_with_all_tools)

    def test_clew_check_stamp_registered(self, mcp_with_all_tools):
        assert "clew_check_stamp" in _get_tools(mcp_with_all_tools)


# ---------------------------------------------------------------------------
# clew_claim_*
# ---------------------------------------------------------------------------


class TestClaimTools:
    def test_claim_add_happy(self, mcp_with_all_tools, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        fn = _get_tools(mcp_with_all_tools)["clew_claim_add"].fn
        out = _run(fn(file_path=str(manuscript), claim_type="statistic"))
        parsed = json.loads(out)
        assert parsed["claim_id"].startswith("claim_")
        assert parsed["claim_type"] == "statistic"

    def test_claim_add_error_on_invalid_type(self, mcp_with_all_tools, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("x")
        fn = _get_tools(mcp_with_all_tools)["clew_claim_add"].fn
        out = _run(fn(file_path=str(manuscript), claim_type="bogus"))
        parsed = json.loads(out)
        assert "error" in parsed

    def test_claim_list_empty(self, mcp_with_all_tools):
        fn = _get_tools(mcp_with_all_tools)["clew_claim_list"].fn
        out = _run(fn())
        parsed = json.loads(out)
        assert parsed["count"] == 0

    def test_claim_verify_not_found(self, mcp_with_all_tools):
        fn = _get_tools(mcp_with_all_tools)["clew_claim_verify"].fn
        out = _run(fn(claim_id_or_location="claim_doesnotexist"))
        parsed = json.loads(out)
        assert parsed["status"] == "not_found"


# ---------------------------------------------------------------------------
# clew_hash_*
# ---------------------------------------------------------------------------


class TestHashTools:
    def test_hash_file_happy(self, mcp_with_all_tools, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("hello")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_file"].fn
        out = _run(fn(path=str(f)))
        parsed = json.loads(out)
        assert parsed["path"] == str(f)
        assert isinstance(parsed["hash"], str) and len(parsed["hash"]) > 0

    def test_hash_file_missing_returns_error(self, mcp_with_all_tools, tmp_path):
        fn = _get_tools(mcp_with_all_tools)["clew_hash_file"].fn
        out = _run(fn(path=str(tmp_path / "nope.txt")))
        parsed = json.loads(out)
        assert "error" in parsed

    def test_hash_directory_happy(self, mcp_with_all_tools, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_directory"].fn
        out = _run(fn(path=str(tmp_path)))
        parsed = json.loads(out)
        assert parsed["count"] >= 2

    def test_hash_directory_not_a_directory_returns_error(
        self, mcp_with_all_tools, tmp_path
    ):
        f = tmp_path / "file.txt"
        f.write_text("x")
        fn = _get_tools(mcp_with_all_tools)["clew_hash_directory"].fn
        out = _run(fn(path=str(f)))
        parsed = json.loads(out)
        assert "error" in parsed


# ---------------------------------------------------------------------------
# clew_stamp_*
# ---------------------------------------------------------------------------


class TestStampTools:
    def test_stamp_with_no_runs_returns_error(self, mcp_with_all_tools):
        fn = _get_tools(mcp_with_all_tools)["clew_stamp"].fn
        out = _run(fn(backend="file"))
        parsed = json.loads(out)
        assert "error" in parsed

    def test_list_stamps_empty(self, mcp_with_all_tools):
        fn = _get_tools(mcp_with_all_tools)["clew_list_stamps"].fn
        out = _run(fn())
        parsed = json.loads(out)
        assert parsed["count"] == 0
        assert parsed["stamps"] == []

    def test_check_stamp_not_found(self, mcp_with_all_tools):
        fn = _get_tools(mcp_with_all_tools)["clew_check_stamp"].fn
        out = _run(fn(stamp_id="bogus_stamp"))
        parsed = json.loads(out)
        # Either 'not_found' or some error key
        assert parsed.get("status") == "not_found" or "error" in parsed


# EOF
