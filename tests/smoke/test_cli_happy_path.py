"""Smoke layer — fast (<60s) subprocess CLI happy-path tests.

No database writes, no network: `--version` / `--help` / `mcp doctor`
only prove the installed `clew` entry point boots and answers.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import scitex_clew

pytestmark = pytest.mark.smoke

_CLEW_BIN = Path(sys.executable).parent / "clew"


@pytest.fixture(autouse=True)
def isolated_cli_home(tmp_path):
    """Point SCITEX_DIR at a throwaway dir and blank the API key.

    Explicit save/restore (PA-306 forbids monkeypatch); a deleted key
    would be repopulated from the real .env via dotenv, so blank it.
    """
    previous = {name: os.environ.get(name) for name in ("SCITEX_DIR", "SCITEX_API_KEY")}
    os.environ["SCITEX_DIR"] = str(tmp_path)
    os.environ["SCITEX_API_KEY"] = " "
    try:
        yield tmp_path
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_cli_version_reports_package_version():
    # Arrange
    # Act
    proc = subprocess.run(
        [str(_CLEW_BIN), "--version"], capture_output=True, text=True, check=True
    )
    # Assert
    assert scitex_clew.__version__ in proc.stdout


def test_cli_help_lists_status_command():
    # Arrange
    # Act
    proc = subprocess.run(
        [str(_CLEW_BIN), "--help"], capture_output=True, text=True, check=True
    )
    # Assert
    assert "status" in proc.stdout


def test_mcp_doctor_reports_ready():
    # Arrange
    # Act
    proc = subprocess.run(
        [str(_CLEW_BIN), "mcp", "doctor"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Assert
    assert "MCP server is ready." in proc.stdout
