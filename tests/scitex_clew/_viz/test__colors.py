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


def test_colors_includes_canonical_ansi_codes_colors_reset_equals_x1b_0m():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.RESET == "\033[0m"


def test_colors_includes_canonical_ansi_codes_colors_bold_equals_x1b_1m():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.BOLD == "\033[1m"


def test_colors_includes_canonical_ansi_codes_colors_red_startswith_x1b():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.RED.startswith("\033[")


def test_colors_includes_canonical_ansi_codes_colors_green_startswith_x1b():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.GREEN.startswith("\033[")




def test_colors_distinct_codes():
    # Arrange
    # Act
    # Arrange
    # Act
    palette = {Colors.GREEN, Colors.RED, Colors.YELLOW, Colors.CYAN, Colors.GRAY}
    # All five must be unique strings.
    # Assert
    # Assert
    assert len(palette) == 5


# ----- VerificationLevel constants ----------------------------------------- #


def test_verification_level_constants_verificationlevel_cache_equals_cache():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert VerificationLevel.CACHE == "cache"


def test_verification_level_constants_verificationlevel_scratch_equals_scratch():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
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
def test_status_icon_default_cache_level_marker_in_icon(status, marker):
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    icon = status_icon(status)
    # Act
    # Assert
    # Assert
    # Assert
    assert marker in icon


@pytest.mark.parametrize(
    "status,marker",
    [
        (VerificationStatus.VERIFIED, "●"),
        (VerificationStatus.MISMATCH, "●"),
        (VerificationStatus.MISSING, "○"),
    ],
)
def test_status_icon_default_cache_level_icon_startswith_x1b(status, marker):
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    icon = status_icon(status)
    # Act
    # Assert
    # Assert
    # Assert
    assert icon.startswith("\033[")


@pytest.mark.parametrize(
    "status,marker",
    [
        (VerificationStatus.VERIFIED, "●"),
        (VerificationStatus.MISMATCH, "●"),
        (VerificationStatus.MISSING, "○"),
    ],
)
def test_status_icon_default_cache_level_icon_endswith_colors_reset(status, marker):
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    icon = status_icon(status)
    # Act
    # Assert
    # Assert
    # Assert
    assert icon.endswith(Colors.RESET)




def test_status_icon_unknown_uses_question_mark():
    # Arrange
    # Act
    # Arrange
    # Act
    out = status_icon(VerificationStatus.UNKNOWN)
    # Assert
    # Assert
    assert "?" in out


def test_status_icon_scratch_verified_renders_double_circle():
    """L2 (re-run) verified gets a double-dot to distinguish from cache."""
    # Arrange
    # Act
    out = status_icon(VerificationStatus.VERIFIED, level=VerificationLevel.SCRATCH)
    # Assert
    assert "●●" in out


def test_status_icon_scratch_only_promotes_verified():
    """Scratch level shouldn't promote MISMATCH/MISSING to ●●."""
    # Arrange
    # Act
    mismatch_out = status_icon(
        VerificationStatus.MISMATCH, level=VerificationLevel.SCRATCH
    )
    # Assert
    assert "●●" not in mismatch_out


def test_status_icon_color_matches_status_colors_green_in_status_icon_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.GREEN in status_icon(VerificationStatus.VERIFIED)


def test_status_icon_color_matches_status_colors_red_in_status_icon_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.RED in status_icon(VerificationStatus.MISMATCH)


def test_status_icon_color_matches_status_colors_yellow_in_status_icon_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.YELLOW in status_icon(VerificationStatus.MISSING)


def test_status_icon_color_matches_status_colors_cyan_in_status_icon_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
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
def test_status_text_word_word_in_text(status, word):
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    text = status_text(status)
    # Act
    # Assert
    # Assert
    # Assert
    assert word in text


@pytest.mark.parametrize(
    "status,word",
    [
        (VerificationStatus.VERIFIED, "verified"),
        (VerificationStatus.MISMATCH, "mismatch"),
        (VerificationStatus.MISSING, "missing"),
        (VerificationStatus.UNKNOWN, "unknown"),
    ],
)
def test_status_text_word_text_endswith_colors_reset(status, word):
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    text = status_text(status)
    # Act
    # Assert
    # Assert
    # Assert
    assert text.endswith(Colors.RESET)




def test_status_text_color_matches_status_colors_green_in_status_text_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.GREEN in status_text(VerificationStatus.VERIFIED)


def test_status_text_color_matches_status_colors_red_in_status_text_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.RED in status_text(VerificationStatus.MISMATCH)


def test_status_text_color_matches_status_colors_yellow_in_status_text_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.YELLOW in status_text(VerificationStatus.MISSING)


def test_status_text_color_matches_status_colors_cyan_in_status_text_verifications():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert Colors.CYAN in status_text(VerificationStatus.UNKNOWN)


# ----- VerificationStatus.SUSPECT (3-colour DAG) -------------------------- #


def test_colors_orange_is_ansi_escape_for_suspect_band():
    # Arrange
    # Act
    # Assert
    assert Colors.ORANGE.startswith("\033[") and "208" in Colors.ORANGE


def test_status_icon_for_suspect_uses_orange():
    # Arrange
    # Act
    icon = status_icon(VerificationStatus.SUSPECT)
    # Assert
    assert Colors.ORANGE in icon and "●" in icon


def test_status_text_for_suspect_uses_orange_word_suspect():
    # Arrange
    # Act
    text = status_text(VerificationStatus.SUSPECT)
    # Assert
    assert Colors.ORANGE in text and "suspect" in text


