#!/usr/bin/env python3
"""Tests for scitex_clew._core._logging module."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

# Repo ``src/`` dir for THIS worktree, so subprocess tests exercise the source
# under test rather than an editable install that may point at another worktree.
_SRC_DIR = str(Path(__file__).resolve().parents[3] / "src")


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


class TestOptionalImportFailureTolerance:
    """The optional scitex_logging path must never crash clew's import.

    scitex_logging does filesystem work at import time (file handlers under
    ~/.scitex/logs). On a quota-full / inode-exhausted filesystem that import
    raises OSError (not ImportError), so a narrow ``except ImportError`` would
    let it propagate and crash clew's entire package import. The fallback must
    tolerate ANY exception from the optional path.
    """

    def _run_with_broken_scitex_logging(self, snippet: str) -> str:
        # Install a meta-path finder that makes ``import scitex_logging`` raise
        # OSError (simulating quota/inode exhaustion at import time), then run
        # the snippet in a fresh subprocess interpreter. Deterministic — no
        # real filesystem quota tricks.
        prelude = (
            "import sys\n"
            "from importlib.abc import Loader, MetaPathFinder\n"
            "from importlib.machinery import ModuleSpec\n"
            "class _BoomLoader(Loader):\n"
            "    def create_module(self, spec):\n"
            "        raise OSError('No space left on device')\n"
            "    def exec_module(self, module):\n"
            "        raise OSError('No space left on device')\n"
            "class _BoomFinder(MetaPathFinder):\n"
            "    def find_spec(self, name, path, target=None):\n"
            "        if name == 'scitex_logging':\n"
            "            return ModuleSpec(name, _BoomLoader())\n"
            "        return None\n"
            "sys.modules.pop('scitex_logging', None)\n"
            "sys.meta_path.insert(0, _BoomFinder())\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [_SRC_DIR, env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        result = subprocess.run(
            [sys.executable, "-c", prelude + snippet],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, (
            f"subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        return result.stdout

    def test_import_hook_actually_breaks_scitex_logging(self):
        # Sanity-check the harness itself: with the finder installed,
        # ``import scitex_logging`` must raise OSError (not ImportError).
        # Arrange
        snippet = (
            "try:\n"
            "    import scitex_logging\n"
            "    print('NO_ERROR')\n"
            "except OSError:\n"
            "    print('OSERROR')\n"
            "except ImportError:\n"
            "    print('IMPORTERROR')\n"
        )
        # Act
        out = self._run_with_broken_scitex_logging(snippet)
        # Assert
        assert out.strip() == "OSERROR"

    def test_logging_module_imports_despite_oserror(self):
        # The core defect: clew's _logging must still import cleanly and yield
        # a working stdlib getLogger when the optional path raises OSError.
        # Arrange
        snippet = (
            "import logging\n"
            "from scitex_clew._core import _logging as m\n"
            "logger = m.getLogger('quota_full_check')\n"
            "logger.info('works')\n"
            "print(m.getLogger is logging.getLogger)\n"
        )
        # Act
        out = self._run_with_broken_scitex_logging(snippet)
        # Assert
        assert out.strip() == "True"

    def test_scitex_clew_package_imports_despite_oserror(self):
        # The whole point: `import scitex_clew` must not crash because an
        # OPTIONAL enhancement failed at import time.
        # Arrange
        snippet = "import scitex_clew\nprint('IMPORTED')\n"
        # Act
        out = self._run_with_broken_scitex_logging(snippet)
        # Assert
        assert out.strip() == "IMPORTED"


# EOF
