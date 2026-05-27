"""Enforces SciTeX skills quality checklist §1–§4.
Canonical: src/scitex/_skills/general/21_scitex-package-quality-checklist.md
"""

from pathlib import Path

import pytest

# PA-303: scitex_dev is in the [dev] extra (not [project] deps).
_skills_quality_pytest = pytest.importorskip("scitex_dev._skills_quality_pytest")
make_skill_quality_tests = _skills_quality_pytest.make_skill_quality_tests

test_skills_quality = make_skill_quality_tests(
    package_root=Path(__file__).resolve().parents[2]
)
