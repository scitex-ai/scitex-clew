#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :mod:`scitex_clew._sources._grounding_api` — the per-claim
grounding verdict wrapping :func:`~scitex_clew._sources._gate.is_grounded`
for a live inline editor (scitex-writer's SSOT paper editor; scitex-todo card
``clew-per-claim-grounding-api``).

Per PA-306 §3 (no mocks): a real isolated DB seeded with real claims, a real
on-disk manifest, and the real chain walk — same discipline as
``test__gate.py``. Per PA-307 §3: AAA markers + one observable fact per test.
"""

from __future__ import annotations

import json
import os

import pytest

import scitex_clew._db as _db_module
from scitex_clew._claim._register import add_claim
from scitex_clew._db import set_db
from scitex_clew._sources import GROUNDING_REASONS
from scitex_clew._sources._gate import is_grounded
from scitex_clew._sources._grounding_api import is_claim_grounded
from scitex_clew._sources._manifest import (
    SOURCES_SCHEMA,
    full_sha256,
    load_sources_manifest,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path):
    """Isolated DB (via ``SCITEX_CLEW_DB_PATH`` — the SAME tier-2 env var
    ``is_claim_grounded``'s own workdir resolution honors) + an isolated
    sources manifest resolved naturally from ``workdir=tmp_path`` (tier-3,
    no env override needed)."""
    db_path = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
    prev_auto = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    prev_db = os.environ.get("SCITEX_CLEW_DB_PATH")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    os.environ["SCITEX_CLEW_DB_PATH"] = str(db_path)
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev_auto is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev_auto
    if prev_db is None:
        os.environ.pop("SCITEX_CLEW_DB_PATH", None)
    else:
        os.environ["SCITEX_CLEW_DB_PATH"] = prev_db


def _manifest_path(root):
    return root / ".scitex" / "clew" / "sources.json"


def _mk(root, rel, content="x\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _write_manifest(root, files, signature=None):
    entries = [
        {"path": str(f.relative_to(root)), "sha256": full_sha256(f)} for f in files
    ]
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema": SOURCES_SCHEMA, "sources": entries, "signature": signature}
        )
    )
    return path


class TestGroundedReason:
    def test_claim_with_registered_source_is_grounded(self, isolated_env, tmp_path):
        # Arrange
        src = _mk(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [src])
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict = is_claim_grounded(claim.claim_id, workdir=str(tmp_path))
        # Assert
        assert verdict == {
            "grounded": True,
            "claim_id": claim.claim_id,
            "matched_source": {"path": "raw.csv", "sha256": full_sha256(src)},
            "reason": "grounded",
            "fix_hint": "",
        }

    def test_location_string_resolves_same_claim(self, isolated_env, tmp_path):
        # Arrange
        src = _mk(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [src])
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act — resolve by "file.tex:L1" location instead of claim_id.
        verdict = is_claim_grounded(f"{paper}:L1", workdir=str(tmp_path))
        # Assert
        assert verdict["claim_id"] == claim.claim_id and verdict["grounded"] is True


class TestNoChainMatch:
    def test_ungrounded_claim_reports_no_chain_match(self, isolated_env, tmp_path):
        # Arrange — manifest active via an UNRELATED source; the claim's own
        # source is not registered and reaches nothing registered.
        unrelated = _mk(tmp_path, "other.csv")
        _write_manifest(tmp_path, [unrelated])
        src = _mk(tmp_path, "handmade.csv", "0.94\n")
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
            source_file=str(src),
        )
        # Act
        verdict = is_claim_grounded(claim.claim_id, workdir=str(tmp_path))
        # Assert
        assert (
            verdict["grounded"] is False
            and verdict["reason"] == "no_chain_match"
            and verdict["matched_source"] is None
            and "register-source" in verdict["fix_hint"]
        )


class TestNoManifest:
    def test_no_manifest_file_reports_grounded_true_amber(
        self, isolated_env, tmp_path
    ):
        # Arrange — NO manifest at all: gate inactive, "compose-phase
        # convenience", NOT a failure.
        src = _mk(tmp_path, "handmade.csv")
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict = is_claim_grounded(claim.claim_id, workdir=str(tmp_path))
        # Assert — never disagrees with the aggregate gate (inactive => never
        # demoted => True here too).
        assert (
            verdict["grounded"] is True
            and verdict["reason"] == "no_manifest"
            and verdict["matched_source"] is None
            and "inactive" in verdict["fix_hint"]
        )


class TestManifestUntrusted:
    def test_unsigned_manifest_under_enforcing_key_is_untrusted(
        self, isolated_env, tmp_path
    ):
        # Arrange — a committed signing.pub ENFORCES signatures; the
        # manifest itself is left unsigned (signature=None).
        from scitex_clew._sources._signing import generate_keypair

        _private_pem, public_pem = generate_keypair()
        pubkey_path = tmp_path / ".scitex" / "clew" / "signed" / "signing.pub"
        pubkey_path.parent.mkdir(parents=True, exist_ok=True)
        pubkey_path.write_bytes(public_pem)

        src = _mk(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [src])  # signature=None -> unsigned
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict = is_claim_grounded(claim.claim_id, workdir=str(tmp_path))
        # Assert
        assert (
            verdict["grounded"] is False
            and verdict["reason"] == "manifest_untrusted"
            and "re-sign" in verdict["fix_hint"]
        )


class TestClaimNotFound:
    def test_unknown_location_reports_claim_not_found(self, isolated_env, tmp_path):
        # Arrange — no claim was ever registered.
        # Act
        verdict = is_claim_grounded("nope_claim_id", workdir=str(tmp_path))
        # Assert
        assert (
            verdict["grounded"] is False
            and verdict["reason"] == "claim_not_found"
            and verdict["claim_id"] == "nope_claim_id"
            and verdict["matched_source"] is None
            and "claim_id or file:line" in verdict["fix_hint"]
        )


class TestHardInvariant:
    """``grounded`` must NEVER disagree with ``is_grounded(...)`` on the same
    claim/manifest/db — the whole reason this API exists (see module
    docstring). Covers the defensive-True-with-no-valid-anchors edge case
    explicitly, per the locked design's HARD invariant.

    One test per manifest-state scenario (not a single parametrized test
    branching on scenario name) — each scenario arranges different fixture
    state but asserts the identical invariant, so this stays three distinct
    tests rather than one function wearing three intents.
    """

    def _resolved(self, isolated_env, tmp_path, claim):
        """Return ``(verdict, expected)`` — no assertion here; each test
        function asserts inline so the audit's per-function AAA/assertion
        check sees a real ``assert`` in every test body, not a delegated
        one."""
        manifest = load_sources_manifest(_manifest_path(tmp_path), root=tmp_path)
        verdict = is_claim_grounded(claim.claim_id, workdir=str(tmp_path))
        expected = is_grounded(claim, manifest, isolated_env)
        return verdict, expected

    def test_matched_source_invariant_holds(self, isolated_env, tmp_path):
        # Arrange — the claim's source is registered and hash-consistent.
        paper = _mk(tmp_path, "p.tex", "v\n")
        src = _mk(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [src])
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict, expected = self._resolved(isolated_env, tmp_path, claim)
        # Assert — the HARD invariant.
        assert verdict["grounded"] is expected

    def test_no_match_invariant_holds(self, isolated_env, tmp_path):
        # Arrange — manifest active via an unrelated source only.
        paper = _mk(tmp_path, "p.tex", "v\n")
        unrelated = _mk(tmp_path, "other.csv")
        _write_manifest(tmp_path, [unrelated])
        src = _mk(tmp_path, "handmade.csv")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict, expected = self._resolved(isolated_env, tmp_path, claim)
        # Assert — the HARD invariant.
        assert verdict["grounded"] is expected

    def test_defensive_true_empty_anchors_invariant_holds(self, isolated_env, tmp_path):
        # Arrange — manifest present + trusted but with ZERO valid anchors.
        paper = _mk(tmp_path, "p.tex", "v\n")
        _write_manifest(tmp_path, [])
        src = _mk(tmp_path, "handmade.csv")
        claim = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="1",
            source_file=str(src),
        )
        # Act
        verdict, expected = self._resolved(isolated_env, tmp_path, claim)
        # Assert — the HARD invariant.
        assert verdict["grounded"] is expected


def test_grounding_reasons_is_stable_and_importable():
    # Arrange
    # (module-level constant — nothing to arrange)
    # Act
    # (nothing to invoke — asserting the imported constant directly)
    # Assert — the frozen reason set downstream consumers (scitex-dev's
    # future provenance_verdict) should import instead of hardcoding strings.
    assert GROUNDING_REASONS == (
        "grounded",
        "no_chain_match",
        "no_manifest",
        "manifest_untrusted",
        "claim_not_found",
    )


# EOF
