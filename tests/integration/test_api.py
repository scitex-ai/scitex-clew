#!/usr/bin/env python3
"""Tests for the minimized clew public API surface."""

import types

import scitex_clew as clew


class TestPublicAPI:
    """Verify __all__ contains the expected public names."""

    def test_all_count_len_clew_all_is_22(self):
        # 21 public names + canonical __version__ string (per PA201)
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert len(clew.__all__) == 22

    def test_all_names_set_clew_all_expected(self):
        # Arrange
        # Act
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
            "add_claim",
            "list_claims",
            "verify_claim",
            "register_intermediate",
            "stamp",
            "list_stamps",
            "check_stamp",
            "hash_file",
            "hash_directory",
            "mermaid",
            "groupers",
            "init_examples",
        }
        # Assert
        # Assert
        assert set(clew.__all__) == expected

    def test_all_names_are_callable(self):
        # Modules in __all__ are namespace exports; __version__ is a string;
        # everything else must be callable.
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        for name in clew.__all__:
            obj = getattr(clew, name)
            if name == "__version__":
                assert isinstance(obj, str), f"{name} should be a version string"
                continue
            assert callable(obj) or isinstance(obj, types.ModuleType), (
                f"{name} is not callable or a module"
            )


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


    def test_old_names_not_in_all(self):
        """Old names are accessible but NOT in __all__."""
        # Arrange
        # Act
        # Assert
        old_names = [
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
        for name in old_names:
            assert name not in clew.__all__, f"{name} should not be in __all__"
            assert hasattr(clew, name), f"{name} should still be accessible"


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
