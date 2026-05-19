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

# PA-303: fastmcp is in the [mcp] extra (not [project] deps).
FastMCP = pytest.importorskip("fastmcp").FastMCP

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


def test_skills_list_excludes_skill_md_out_success_is_true(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["success"] is True


def test_skills_list_excludes_skill_md_out_package_scitex_clew(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["package"] == "scitex-clew"


def test_skills_list_excludes_skill_md_skill_not_in_out_skills(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert "SKILL" not in out["skills"]


def test_skills_list_excludes_skill_md_set_out_skills_01_quick_start_02_grouping_10_advanced(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert set(out["skills"]) == {"01_quick-start", "02_grouping", "10_advanced"}




def test_skills_list_returns_sorted(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Assert
    # Assert
    assert out["skills"] == sorted(out["skills"])


def test_skills_list_empty_dir_out_success_is_true(tmp_path, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["success"] is True


def test_skills_list_empty_dir_out_skills(tmp_path, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["skills"] == []




def test_skills_list_handles_missing_dir_out_success_is_true(tmp_path, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path / "doesnotexist")
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["success"] is True


def test_skills_list_handles_missing_dir_out_skills(tmp_path, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, tmp_path / "doesnotexist")
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_list")())
    # Act
    # Assert
    # Assert
    # Assert
    assert out["skills"] == []




# ----- clew_skills_get ----------------------------------------------------- #


def test_skills_get_returns_content_out_success_is_true(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    # Act
    # Assert
    # Assert
    # Assert
    assert out["success"] is True


def test_skills_get_returns_content_out_package_scitex_clew(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    # Act
    # Assert
    # Assert
    # Assert
    assert out["package"] == "scitex-clew"


def test_skills_get_returns_content_out_name_01_quick_start(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    # Act
    # Assert
    # Assert
    # Assert
    assert out["name"] == "01_quick-start"


def test_skills_get_returns_content_quick_start_in_out_content(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    # Act
    # Assert
    # Assert
    # Assert
    assert "Quick Start" in out["content"]


def test_skills_get_returns_content_body_1_in_out_content(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="01_quick-start"))
    # Act
    # Assert
    # Assert
    # Assert
    assert "body-1" in out["content"]




def test_skills_get_unknown_name_out_success_is_false(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="nonexistent"))
    # Act
    # Assert
    # Assert
    # Assert
    assert out["success"] is False


def test_skills_get_unknown_name_unknown_skill_in_out_error(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="nonexistent"))
    # Act
    # Assert
    # Assert
    # Assert
    assert "unknown skill" in out["error"]


def test_skills_get_unknown_name_n_01_quick_start_in_out_error(skills_tmp, monkeypatch):
    # Arrange
    # Arrange
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="nonexistent"))
    # Act
    # Assert
    # Assert
    # Assert
    assert "01_quick-start" in out["error"]




def test_skills_get_payload_round_trip(skills_tmp, monkeypatch):
    """Returned content must equal the literal file contents byte-for-byte."""
    # Arrange
    mcp = FastMCP(name="clew-test")
    _register_against_dir(mcp, monkeypatch, skills_tmp)
    # Act
    out = json.loads(_get_tool(mcp, "clew_skills_get")(name="10_advanced"))
    # Assert
    assert out["content"] == (skills_tmp / "10_advanced.md").read_text()
