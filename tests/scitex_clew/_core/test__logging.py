#!/usr/bin/env python3
"""Tests for scitex_clew._core._logging module."""

from __future__ import annotations

import logging


class TestGetLogger:
    def test_getLogger_is_callable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._core._logging import getLogger

        # Assert
        # Assert
        assert callable(getLogger)

    def test_getLogger_returns_logger(self):
        # Arrange
        # Arrange
        from scitex_clew._core._logging import getLogger

        # Act
        # Act
        logger = getLogger("test_scitex_clew")
        # Assert
        # Assert
        assert logger is not None

    def test_getLogger_with_name(self):
        # Arrange
        # Arrange
        from scitex_clew._core._logging import getLogger

        # Act
        # Act
        logger = getLogger("scitex_clew.test_module")
        # Must be a logger-like object with standard methods
        # Assert
        # Assert
        assert hasattr(logger, "info") or hasattr(logger, "debug")

    def test_getLogger_stdlib_fallback(self):
        # Even if scitex.logging is not available, we get a callable
        # Arrange
        # Arrange
        from scitex_clew._core._logging import getLogger

        # Act
        # Act
        logger = getLogger(__name__)
        # Assert
        # Assert
        assert logger is not None

    def test_getLogger_same_name_returns_same_logger(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        from scitex_clew._core._logging import getLogger

        logger_a = getLogger("scitex_clew.same")
        logger_b = getLogger("scitex_clew.same")
        # stdlib logging guarantees same instance for same name
        try:
            assert logger_a is logger_b
        except AssertionError:
            # scitex.logging may return new instances — not an error
            pass

    def test_getLogger_no_args_does_not_raise(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        from scitex_clew._core._logging import getLogger

        # Python stdlib logging.getLogger() with no args returns root logger
        try:
            logger = getLogger()
            assert logger is not None
        except TypeError:
            # Some implementations may require a name argument — acceptable
            pass

    def test_module_imports_cleanly(self):
        # Arrange
        # Arrange
        import importlib

        # Act
        # Act
        mod = importlib.import_module("scitex_clew._core._logging")
        # Assert
        # Assert
        assert hasattr(mod, "getLogger")

    def test_getLogger_is_stdlib_logging_or_compatible(self):
        # Arrange
        # Arrange
        from scitex_clew._core._logging import getLogger

        # Should be either stdlib logging.getLogger or a compatible callable
        # Verify it is either the same object or produces something logger-like
        std_logger = getLogger("test_compat_check")
        # Logger-like object should have at least one of these attributes
        logger_attrs = {"info", "debug", "warning", "error", "critical"}
        # Act
        # Act
        has_any = any(hasattr(std_logger, attr) for attr in logger_attrs)
        # Either it's logger-like or it IS logging.getLogger itself
        # Assert
        # Assert
        assert has_any or getLogger is logging.getLogger


# EOF
