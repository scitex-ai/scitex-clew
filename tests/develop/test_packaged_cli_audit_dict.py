"""The packaged CLI-audit dictionary must be a byte-identical copy of the source.

``.scitex/dev/cli-audit-dict.yaml`` is the edited source of truth;
``src/scitex_clew/_cli_audit_dict.yaml`` is the copy force-included into the
wheel/sdist. The release build (``.github/ci/check-dist.py``) refuses to build
when they differ, so a drift merged to develop only surfaced at tag time
(v0.22.0: the ``slice`` verb was declared in the source but not the copy).
Checking it here makes PR CI catch the drift before release.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".scitex" / "dev" / "cli-audit-dict.yaml"
PACKAGED = ROOT / "src" / "scitex_clew" / "_cli_audit_dict.yaml"


def test_packaged_cli_audit_dict_matches_source():
    # Arrange
    expected = SOURCE.read_bytes()
    # Act
    actual = PACKAGED.read_bytes()
    # Assert
    assert actual == expected, (
        f"{PACKAGED.relative_to(ROOT)} drifted from {SOURCE.relative_to(ROOT)}; "
        "copy the source over the packaged resource"
    )
