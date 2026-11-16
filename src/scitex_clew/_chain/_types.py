#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_types.py
"""Verification dataclasses and enumerations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class VerificationStatus(Enum):
    """Verification status for a run or file.

    SUSPECT is a specialization of MISMATCH for runs where every local file
    verifies on its own (hashes match the recorded values) but at least one
    UPSTREAM session that produced an input failed. The run itself is
    locally valid; the chain is not. Surfaces as a third colour
    ("upstream-failed-but-locally-valid", typically orange) so the DAG view
    can distinguish a locally-broken run from a chain-broken-only run.

    Callers that want the legacy 2-state colouring (treat upstream-only
    failures the same as local failures) opt back in via the
    ``collapse_suspect`` knob on the helpers that emit this enum — the
    default emits SUSPECT.

    FAILED marks a run whose recorded execution status is ``failed`` /
    ``error``: whatever files it left behind are not evidence, so it is never
    VERIFIED regardless of how its file hashes compare. Downstream consumers
    of a FAILED run's outputs are SUSPECT.
    """

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    SUSPECT = "suspect"
    FAILED = "failed"
    MISSING = "missing"
    UNKNOWN = "unknown"


class VerificationLevel(Enum):
    """Level of verification performed.

    L1: CACHE     — Compare stored hashes vs current files (local only)
    L2: RERUN     — Re-execute pipeline and compare (local only)
    L3: REGISTERED — L2 + hash registered in Clew Registry with timestamp (scitex.ai)
    """

    CACHE = "cache"  # L1: Hash comparison only (fast)
    RERUN = "rerun"  # L2: Full re-execution (thorough)
    REGISTERED = "registered"  # L3: Registered with server-side timestamp


@dataclass
class FileVerification:
    """Verification result for a single file."""

    path: str
    role: str
    expected_hash: str
    current_hash: str | None
    status: VerificationStatus
    frozen: bool = False
    """True when verification trusted the recorded hash without re-reading the file.

    A frozen FileVerification counts as passing for chain purposes (it does not
    block the run) but is NEVER conflated with a fully hash-verified result —
    the flag propagates to CLI output and Mermaid nodes so the trust is always
    explicit and visible.
    """

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED


@dataclass
class RunVerification:
    """Verification result for a session run."""

    session_id: str
    script_path: str | None
    status: VerificationStatus
    files: list[FileVerification]
    combined_hash_expected: str | None
    combined_hash_current: str | None
    level: VerificationLevel = VerificationLevel.CACHE
    provenance: str = "tracked"
    exception_reason: str | None = None

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    @property
    def is_verified_from_scratch(self) -> bool:
        return self.is_verified and self.level == VerificationLevel.RERUN

    @property
    def inputs(self) -> list[FileVerification]:
        return [f for f in self.files if f.role == "input"]

    @property
    def outputs(self) -> list[FileVerification]:
        return [f for f in self.files if f.role == "output"]

    @property
    def mismatched_files(self) -> list[FileVerification]:
        return [f for f in self.files if f.status == VerificationStatus.MISMATCH]

    @property
    def missing_files(self) -> list[FileVerification]:
        return [f for f in self.files if f.status == VerificationStatus.MISSING]


@dataclass
class ChainVerification:
    """Verification result for a dependency chain."""

    target_file: str
    runs: list[RunVerification]
    status: VerificationStatus

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    @property
    def failed_runs(self) -> list[RunVerification]:
        return [r for r in self.runs if not r.is_verified]


@dataclass
class DAGVerification:
    """Verification result for a multi-target DAG."""

    target_files: list[str]
    runs: list[RunVerification]
    edges: list[tuple[str, str]]  # (parent_sid, child_sid)
    status: VerificationStatus
    topological_order: list[str]

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    @property
    def failed_runs(self) -> list[RunVerification]:
        return [r for r in self.runs if not r.is_verified]


# EOF
