#!/usr/bin/env python3
"""Tests for the minimized clew public API surface."""

import types

import scitex_clew as clew


class TestPublicAPI:
    """Verify __all__ contains the expected public names."""

    def test_all_count_len_clew_all_is_29(self):
        # 26 public names + canonical __version__ string (per PA201).
        # +1 over the previous 26 for ``estimate`` (the Phase 1 pre-flight
        # compute estimate, 2026-06-27). ``EstimateResult`` is intentionally
        # lazy-only (not in __all__), matching the other result dataclasses.
        # +2 for ``remove_claim`` and ``supersede_claim`` (2026-06-30).
        # Arrange
        # Act
        # Assert
        assert len(clew.__all__) == 29

    def test_all_names_set_clew_all_expected(self):
        # Arrange
        # Act
        expected = {
            "__version__",
            "status",
            "run",
            "chain",
            "dag",
            "rerun",
            "rerun_dag",
            "rerun_claims",
            "list_runs",
            "stats",
            "estimate",
            "add_claim",
            "list_claims",
            "verify_claim",
            "verify_all_claims",
            "export_claims_json",
            "register_intermediate",
            "remove_claim",
            "supersede_claim",
            "stamp",
            "list_stamps",
            "check_stamp",
            "hash_file",
            "hash_directory",
            "mermaid",
            "groupers",
            "init_examples",
            "on_session_start",
            "on_session_close",
        }
        # Assert
        assert set(clew.__all__) == expected

    def test_version_in_all_is_a_string(self):
        # __version__ is the lone non-callable in __all__ — it must be a string.
        # Arrange
        # Act
        version = getattr(clew, "__version__", None)
        # Assert
        assert isinstance(version, str)

    def test_all_non_version_names_are_callable_or_module(self):
        # Modules in __all__ are namespace exports; everything else (besides
        # __version__) must be callable.
        # Arrange
        names = [n for n in clew.__all__ if n != "__version__"]
        # Act
        bad = [
            name
            for name in names
            if not (
                callable(getattr(clew, name))
                or isinstance(getattr(clew, name), types.ModuleType)
            )
        ]
        # Assert
        assert bad == []


class TestBackwardCompat:
    """Old names still accessible as attributes (not in __all__)."""

    def test_verify_run_callable_clew_verify_run(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.verify_run)

    def test_verify_chain_callable_clew_verify_chain(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.verify_chain)

    def test_verify_dag_callable_clew_verify_dag(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.verify_dag)

    def test_verify_by_rerun(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.verify_by_rerun)

    def test_verify_run_from_scratch(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.verify_run_from_scratch)

    def test_get_db_callable_clew_get_db(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.get_db)

    def test_set_db_callable_clew_set_db(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.set_db)

    def test_get_status_callable_clew_get_status(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.get_status)

    def test_get_tracker_callable_clew_get_tracker(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.get_tracker)

    def test_format_status_callable_clew_format_status(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.format_status)

    def test_generate_mermaid_dag(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.generate_mermaid_dag)

    def test_render_dag_callable_clew_render_dag(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.render_dag)

    def test_verification_status_enum(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert hasattr(clew.VerificationStatus, "VERIFIED")

    def test_verification_level_enum_hasattr_clew_verificationlevel_cache(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert hasattr(clew.VerificationLevel, "CACHE")

    def test_verification_level_enum_hasattr_clew_verificationlevel_rerun(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert hasattr(clew.VerificationLevel, "RERUN")

    def test_classes_accessible_clew_verificationdb_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.VerificationDB is not None

    def test_classes_accessible_clew_sessiontracker_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.SessionTracker is not None

    def test_classes_accessible_clew_clewregistry_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.ClewRegistry is not None

    def test_classes_accessible_clew_runverification_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.RunVerification is not None

    def test_classes_accessible_clew_chainverification_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.ChainVerification is not None

    def test_classes_accessible_clew_dagverification_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.DAGVerification is not None

    def test_classes_accessible_clew_fileverification_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.FileVerification is not None

    def test_classes_accessible_clew_claim_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.Claim is not None

    def test_classes_accessible_clew_stamp_is_not_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert clew.Stamp is not None

    OLD_NAMES = [
        "verify_run",
        "verify_chain",
        "verify_dag",
        "verify_by_rerun",
        "get_db",
        "set_db",
        "get_status",
        "get_tracker",
        "format_status",
        "generate_mermaid_dag",
        "render_dag",
        "VerificationDB",
        "SessionTracker",
        "VerificationStatus",
    ]

    def test_old_names_excluded_from_all(self):
        """Old names must not appear in clew.__all__."""
        # Arrange
        leaked = [n for n in self.OLD_NAMES if n in clew.__all__]
        # Act
        # Assert
        assert leaked == []

    def test_old_names_still_accessible(self):
        """Old names must remain accessible as attributes for backward compat."""
        # Arrange
        missing = [n for n in self.OLD_NAMES if not hasattr(clew, n)]
        # Act
        # Assert
        assert missing == []


class TestConvenienceFunctions:
    """Convenience functions delegate to internal implementations."""

    def test_rerun_is_callable(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.rerun)

    def test_mermaid_is_callable(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.mermaid)

    def test_rerun_dag_is_callable(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.rerun_dag)

    def test_rerun_claims_is_callable(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert callable(clew.rerun_claims)


# EOF
