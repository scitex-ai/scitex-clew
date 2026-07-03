#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :mod:`scitex_clew._claim._model` — the status palette + resolver.

Two concerns:

1. The registered-source gate resolver: ``_resolve_status`` / the new
   ``grounded`` opt-in parameter and its precedence (schema v1.4).
2. The 8-state CUD (colour-universal-design) delta-E floor: the new
   ``unsourced`` amber must stay perceptually distinct from all 7 locked
   states across normal + protan/deutan/tritan vision (Machado-2009,
   severity 1.0) at the same CIE76 threshold the locked palette already
   satisfies (>= 12).

Per PA-306 §3: no mocks — the colour maths is a pure, self-contained
reimplementation (Machado matrices + sRGB→Lab), no external deps.
"""

from __future__ import annotations

import itertools
import math

from scitex_clew._claim._model import (
    _CLAIM_PALETTE,
    _DISPLAY_GROUPS,
    _DISPLAY_PALETTE,
    _resolve_display_group,
    _resolve_status,
)

# --------------------------------------------------------------------------- #
# 1. Registered-source gate resolver (schema v1.4)
# --------------------------------------------------------------------------- #


class TestResolveStatusGate:
    def test_gate_inactive_leaves_verified_verified(self):
        # Arrange — grounded=None => gate inactive (opt-in).
        # Act
        resolved = _resolve_status("verified", False, False, None)
        # Assert — identical to schema v1.3 (zero behavior change).
        assert resolved == "verified"

    def test_gate_inactive_leaves_registered_registered(self):
        # Arrange
        # Act
        resolved = _resolve_status("registered", False, False, None)
        # Assert
        assert resolved == "registered"

    def test_ungrounded_demotes_verified_to_unsourced(self):
        # Arrange — the false-green guard: link-verified but ungrounded.
        # Act
        resolved = _resolve_status("verified", False, False, False)
        # Assert
        assert resolved == "unsourced"

    def test_ungrounded_demotes_suspect_to_unsourced(self):
        # Arrange — unsourced outranks suspect.
        # Act
        resolved = _resolve_status("suspect", False, False, False)
        # Assert
        assert resolved == "unsourced"

    def test_grounded_verified_stays_verified(self):
        # Arrange
        # Act
        resolved = _resolve_status("verified", False, False, True)
        # Assert
        assert resolved == "verified"

    def test_mismatch_outranks_unsourced(self):
        # Arrange — hash failure beats the source gate (red, not amber).
        # Act
        resolved = _resolve_status("mismatch", False, False, False)
        # Assert
        assert resolved == "mismatch"

    def test_missing_outranks_unsourced(self):
        # Arrange
        # Act
        resolved = _resolve_status("missing", False, False, False)
        # Assert
        assert resolved == "missing"

    def test_grounded_verified_exception_still_exception(self):
        # Arrange — grounded True falls through to existing full-7 logic.
        # Act
        resolved = _resolve_status("verified", True, False, True)
        # Assert
        assert resolved == "exception"

    def test_display_group_unsourced_is_own_bucket(self):
        # Arrange
        # Act
        group = _resolve_display_group("verified", False, False, False)
        # Assert — NOT verified, NOT failed — its own reader bucket.
        assert group == "unsourced"


class TestPaletteMembership:
    def test_claim_palette_has_unsourced_amber(self):
        # Arrange
        key = "unsourced"
        # Act
        hue = _CLAIM_PALETTE[key]
        # Assert
        assert hue == "b26a00"

    def test_display_palette_has_unsourced(self):
        # Arrange
        key = "unsourced"
        # Act
        hue = _DISPLAY_PALETTE[key]
        # Assert
        assert hue == "b26a00"

    def test_display_groups_maps_unsourced_to_itself(self):
        # Arrange
        key = "unsourced"
        # Act
        group = _DISPLAY_GROUPS[key]
        # Assert
        assert group == "unsourced"

    def test_palette_has_exactly_eight_states(self):
        # Arrange
        palette = _CLAIM_PALETTE
        # Act
        n = len(palette)
        # Assert
        assert n == 8


# --------------------------------------------------------------------------- #
# 2. CUD delta-E floor — 8 states, 28 pairs, 4 vision conditions
# --------------------------------------------------------------------------- #

# Machado-2009 CVD matrices at severity 1.0 (applied in LINEAR sRGB).
_MACHADO = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}

# The locked-palette floor: CIE76 >= 12 is the tightest existing pair
# (mismatch/missing under protanopia == 12.12). The 8th state must not
# lower it.
_CUD_THRESHOLD = 12.0


def _hex_to_rgb(h):
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _apply_cvd(rgb, mat):
    lin = [_srgb_to_lin(c) for c in rgb]
    out = [sum(mat[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return tuple(_lin_to_srgb(c) for c in out)


def _rgb_to_lab(rgb):
    r, g, b = (_srgb_to_lin(c) for c in rgb)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _lab(hex_value, cond):
    rgb = _hex_to_rgb(hex_value)
    if cond != "normal":
        rgb = _apply_cvd(rgb, _MACHADO[cond])
    return _rgb_to_lab(rgb)


def _de76(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


class TestCudPaletteEightState:
    def test_all_28_pairs_clear_threshold_across_all_conditions(self):
        # Arrange — every unordered pair of the 8 locked hues.
        conditions = ("normal", "protan", "deutan", "tritan")
        # Act — the minimum CIE76 distance over all pairs x all conditions.
        worst = math.inf
        worst_pair = None
        for a, b in itertools.combinations(_CLAIM_PALETTE, 2):
            for cond in conditions:
                d = _de76(_lab(_CLAIM_PALETTE[a], cond), _lab(_CLAIM_PALETTE[b], cond))
                if d < worst:
                    worst = d
                    worst_pair = (a, b, cond)
        # Assert — no pair drops below the locked-palette floor.
        assert worst >= _CUD_THRESHOLD, f"{worst_pair} = {worst:.2f} < {_CUD_THRESHOLD}"

    def test_unsourced_clears_threshold_against_suspect(self):
        # Arrange — the near-hue risk the spec flagged (amber vs amber).
        conditions = ("normal", "protan", "deutan", "tritan")
        # Act
        worst = min(
            _de76(_lab("b26a00", c), _lab("d29922", c)) for c in conditions
        )
        # Assert
        assert worst >= _CUD_THRESHOLD

    def test_adding_unsourced_does_not_lower_existing_floor(self):
        # Arrange — the 7 locked hues alone.
        conditions = ("normal", "protan", "deutan", "tritan")
        seven = {k: v for k, v in _CLAIM_PALETTE.items() if k != "unsourced"}

        def floor(pal):
            return min(
                _de76(_lab(pal[a], c), _lab(pal[b], c))
                for a, b in itertools.combinations(pal, 2)
                for c in conditions
            )

        # Act
        floor7 = floor(seven)
        floor8 = floor(_CLAIM_PALETTE)
        # Assert — the 8th state does not reduce the palette-wide minimum.
        assert floor8 >= floor7 - 1e-9


# EOF
