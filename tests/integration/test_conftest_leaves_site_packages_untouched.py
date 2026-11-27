"""Regression test: importing tests/conftest.py must not touch site-packages."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_conftest_leaves_site_packages_untouched():
    # Arrange
    conftest = Path(__file__).resolve().parents[1] / "conftest.py"
    assert conftest.is_file()
    child_code = textwrap.dedent(
        f"""\
        import os
        import runpy
        import site

        os.environ["COVERAGE_PROCESS_START"] = "SENTINEL_PROCESS_START"
        os.environ["COVERAGE_FILE"] = "SENTINEL_COVERAGE_FILE"

        def _snapshot():
            names = set()
            dirs = list(site.getsitepackages())
            usersite = site.getusersitepackages()
            if isinstance(usersite, str):
                dirs.append(usersite)
            for d in dirs:
                try:
                    for name in os.listdir(d):
                        names.add((d, name))
                except OSError:
                    continue
            return names

        _before = _snapshot()
        runpy.run_path({str(conftest)!r}, run_name="test_conftest_import")
        _after = _snapshot()
        assert _before == _after, (
            "conftest.py modified site-packages: "
            f"{{sorted(str(p) for p in _after - _before)}}"
        )
        assert os.environ["COVERAGE_PROCESS_START"] == "SENTINEL_PROCESS_START"
        assert os.environ["COVERAGE_FILE"] == "SENTINEL_COVERAGE_FILE"
        """
    )

    # Act
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        capture_output=True,
        text=True,
    )

    # Assert
    assert result.returncode == 0, (
        f"child interpreter failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
