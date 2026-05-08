"""Tests for ``scitex_clew._mcp.tools.skills`` MCP introspection tools.

The two tools (`clew_skills_list`, `clew_skills_get`) close over a
filesystem path resolved at import time, so we patch
`_SKILLS_DIR` to a tmp dir and re-register the tools against a
fresh FastMCP instance per test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import FastMCP

from scitex_clew._mcp.tools import skills as skills_mod
from scitex_clew._mcp.tools.skills import register_tools


def _register_against_dir(mcp: FastMCP, monkeypatch, dir_: Path) -> None:
    """Repoint `_SKILLS_DIR` then register tools so they capture the patch."""
    monkeypatch.setattr(skills_mod, "_SKILLS_DIR", dir_)
    register_tools(mcp)


def _get_tool(mcp: FastMCP, name: str):
    """Pull a registered tool's underlying function out of FastMCP.

    FastMCP 2.x stores tools as `FunctionTool` instances retrievable via
    the async `mcp.get_tool(name)`. We unwrap the awaitable here so each
    test can call the resulting function synchronously.
    """
    import asyncio

    tool = asyncio.run(mcp.get_tool(name))
    return tool.fn


@pytest.fixture
def skills_tmp(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text("# Index — should be excluded")
    (tmp_path / "01_quick-start.md").write_text("# Quick Start\nbody-1")
    (tmp_path / "02_grouping.md").write_text("# Grouping\nbody-2")
    (tmp_path / "10_advanced.md").write_text("# Advanced\nbody-10")
    return tmp_path


# ----- clew_skills_list ---------------------------------------------------- #


def test_skills_list_excludes_skill_md(skills_tmp, monkeypatch):
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    assert out["success"] is True
    assert out["package"] == "scitex-clew"
    assert "SKILL" not in out["skills"]
    assert set(out["skills"]) == {"01_quick-start", "02_grouping", "10_advanced"}


def test_skills_list_returns_sorted(skills_tmp, monkeypatch):
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    assert out["skills"] == sorted(out["skills"])


def test_skills_list_empty_dir(tmp_path, monkeypatch):
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path)
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    assert out["success"] is True
    assert out["skills"] == []


def test_skills_list_handles_missing_dir(tmp_path, monkeypatch):
    """Pointing at a non-existent dir → success with empty list (glob no-ops)."""
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path / "doesnotexist")
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    assert out["success"] is True
    assert out["skills"] == []


# ----- clew_skills_get ----------------------------------------------------- #


def test_skills_get_returns_content(skills_tmp, monkeypatch):
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    assert out["success"] is True
    assert out["package"] == "scitex-clew"
    assert out["name"] == "01_quick-start"
    assert "Quick Start" in out["content"]
    assert "body-1" in out["content"]


def test_skills_get_unknown_name(skills_tmp, monkeypatch):
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="nonexistent"))
    assert out["success"] is False
    assert "unknown skill" in out["error"]
    # Available list is mentioned in the error.
    assert "01_quick-start" in out["error"]


def test_skills_get_payload_round_trip(skills_tmp, monkeypatch):
    """Returned content must equal the literal file contents byte-for-byte."""
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="10_advanced"))
    assert out["content"] == (skills_tmp / "10_advanced.md").read_text()
