"""Tests for ``scitex_clew._viz._colors`` (Colors, status_icon, status_text)."""

from __future__ import annotations

import pytest

from scitex_clew._chain import VerificationStatus
from scitex_clew._viz._colors import (
    Colors,
    VerificationLevel,
    status_icon,
    status_text,
)


# ----- Colors palette ------------------------------------------------------ #


def test_colors_includes_canonical_ansi_codes():
    assert Colors.RESET == "\033[0m"
    assert Colors.BOLD == "\033[1m"
    # Foreground colours start with ESC[9?m
    assert Colors.RED.startswith("\033[")
    assert Colors.GREEN.startswith("\033[")


def test_colors_distinct_codes():
    palette = {Colors.GREEN, Colors.RED, Colors.YELLOW, Colors.CYAN, Colors.GRAY}
    # All five must be unique strings.
    assert len(palette) == 5


# ----- VerificationLevel constants ----------------------------------------- #


def test_verification_level_constants():
    assert VerificationLevel.CACHE == "cache"
    assert VerificationLevel.SCRATCH == "scratch"


# ----- status_icon --------------------------------------------------------- #


@pytest.mark.parametrize(
    "status,marker",
    [
        (VerificationStatus.VERIFIED, "●"),
        (VerificationStatus.MISMATCH, "●"),
        (VerificationStatus.MISSING, "○"),
    ],
)
def test_status_icon_default_cache_level(status, marker):
    icon = status_icon(status)
    assert marker in icon
    # Coloured: contains an ANSI prefix and a reset suffix.
    assert icon.startswith("\033[")
    assert icon.endswith(Colors.RESET)


def test_status_icon_unknown_uses_question_mark():
    out = status_icon(VerificationStatus.UNKNOWN)
    assert "?" in out


def test_status_icon_scratch_verified_renders_double_circle():
    """L2 (re-run) verified gets a double-dot to distinguish from cache."""
    out = status_icon(VerificationStatus.VERIFIED, level=VerificationLevel.SCRATCH)
    assert "●●" in out


def test_status_icon_scratch_only_promotes_verified():
    """Scratch level shouldn't promote MISMATCH/MISSING to ●●."""
    mismatch_out = status_icon(
        VerificationStatus.MISMATCH, level=VerificationLevel.SCRATCH
    )
    assert "●●" not in mismatch_out


def test_status_icon_color_matches_status():
    assert Colors.GREEN in status_icon(VerificationStatus.VERIFIED)
    assert Colors.RED in status_icon(VerificationStatus.MISMATCH)
    assert Colors.YELLOW in status_icon(VerificationStatus.MISSING)
    assert Colors.CYAN in status_icon(VerificationStatus.UNKNOWN)


# ----- status_text --------------------------------------------------------- #


@pytest.mark.parametrize(
    "status,word",
    [
        (VerificationStatus.VERIFIED, "verified"),
        (VerificationStatus.MISMATCH, "mismatch"),
        (VerificationStatus.MISSING, "missing"),
        (VerificationStatus.UNKNOWN, "unknown"),
    ],
)
def test_status_text_word(status, word):
    text = status_text(status)
    assert word in text
    assert text.endswith(Colors.RESET)


def test_status_text_color_matches_status():
    assert Colors.GREEN in status_text(VerificationStatus.VERIFIED)
    assert Colors.RED in status_text(VerificationStatus.MISMATCH)
    assert Colors.YELLOW in status_text(VerificationStatus.MISSING)
    assert Colors.CYAN in status_text(VerificationStatus.UNKNOWN)
