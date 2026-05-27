#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP-tool tests for clew_register_intermediate."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db

_FAKE_SESSION = "2026Y-05M-27D-00h00m00s_Test-main"


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
    set_db(tmp_path / "mcp_register_intermediate.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def mcp_with_all_tools():
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP

    from scitex_clew._mcp.tools import register_all_tools

    m = FastMCP(name="t-register-intermediate")
    register_all_tools(m)
    return m


@pytest.fixture
def no_session_env():
    """Ensure $SCITEX_SESSION_ID is absent, restoring any prior value."""
    saved = os.environ.pop("SCITEX_SESSION_ID", None)
    yield
    if saved is not None:
        os.environ["SCITEX_SESSION_ID"] = saved


class TestRegistration:
    def test_clew_register_intermediate_registered(self, mcp_with_all_tools):
        # Arrange
        tools = _get_tools(mcp_with_all_tools)
        # Act
        present = "clew_register_intermediate" in tools
        # Assert
        assert present


class TestBehavior:
    def test_explicit_session_returns_claim_id(self, mcp_with_all_tools):
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_register_intermediate"].fn
        # Act
        out = _run(
            fn(name="n_sig", value="42", supports="a,b", session_id=_FAKE_SESSION)
        )
        # Assert
        assert json.loads(out)["claim_id"].startswith("claim_")

    def test_missing_session_returns_error(self, mcp_with_all_tools, no_session_env):
        # Arrange
        fn = _get_tools(mcp_with_all_tools)["clew_register_intermediate"].fn
        # Act
        out = _run(fn(name="x", value="1"))
        # Assert
        assert "error" in json.loads(out)


# EOF
