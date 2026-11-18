#!/usr/bin/env python3
"""Non-reproducible environment requirements (:mod:`scitex_clew._chain._env_requirements`).

The E2 replay failure: a run imported a dependency that was patched and
rebuilt locally; its record said ``name==version``, which looked identical
to the index release, and a replay with the index release failed. Here the
record is the REAL scitex-session collector run over REAL distributions
installed by a real ``pip`` (offline, a fresh venv per test session): a tiny
package built by an in-tree PEP 517 backend and installed from a wheelhouse
(index-like), from a local directory, edited in place, and as a patched
rebuild of the same version. Real PostgreSQL store, no mocks; subprocesses
get an explicit environment, never ``os.environ``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
import warnings
from importlib.metadata import distributions
from pathlib import Path

import pytest
import scitex_clew as clew
from scitex_clew._chain._env_requirements import (
    current_distribution,
    environment_findings,
    record_fingerprint,
)
from scitex_clew._chain._slice import build_slice
from scitex_clew._db._paths import project_root
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker

session_dp = pytest.importorskip(
    "scitex_session._lifecycle._dist_provenance",
    reason="needs scitex-session >= 0.5.0 (package_provenance)",
)

NAME = "tinydist_clew_probe"

BACKEND = """
import base64, hashlib, os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME, VERSION = "tinydist_clew_probe", "1.0.0"


def _hash(data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return "sha256=" + digest.decode()


def _wheel(wheel_directory, files):
    info = f"{NAME}-{VERSION}.dist-info"
    files = dict(files)
    files[f"{info}/METADATA"] = (
        f"Metadata-Version: 2.1\\nName: {NAME}\\nVersion: {VERSION}\\n".encode()
    )
    files[f"{info}/WHEEL"] = (
        b"Wheel-Version: 1.0\\nGenerator: probe\\nRoot-Is-Purelib: true\\n"
        b"Tag: py3-none-any\\n"
    )
    files[f"{info}/top_level.txt"] = f"{NAME}\\n".encode()
    record = "".join(f"{p},{_hash(d)},{len(d)}\\n" for p, d in files.items())
    files[f"{info}/RECORD"] = (record + f"{info}/RECORD,,\\n").encode()
    name = f"{NAME}-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(os.path.join(wheel_directory, name), "w") as zf:
        for path, data in files.items():
            zf.writestr(path, data)
    return name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    pkg = os.path.join(HERE, NAME)
    files = {
        f"{NAME}/{f}": open(os.path.join(pkg, f), "rb").read()
        for f in sorted(os.listdir(pkg))
        if f.endswith(".py")
    }
    return _wheel(wheel_directory, files)


def get_requires_for_build_wheel(config_settings=None):
    return []
"""

PYPROJECT = """[build-system]
requires = []
build-backend = "probe_backend"
backend-path = ["."]
"""


def _env(home: Path) -> dict:
    """Explicit subprocess environment (never ``os.environ``)."""
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PIP_NO_INPUT": "1",
    }


def _project(root: Path, body: str) -> Path:
    (root / NAME).mkdir(parents=True)
    (root / NAME / "__init__.py").write_text(body)
    (root / "probe_backend.py").write_text(BACKEND)
    (root / "pyproject.toml").write_text(PYPROJECT)
    return root


def _wheelhouse(project: Path, out: Path) -> Path:
    out.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location(
        f"probe_backend_{uuid.uuid4().hex}", project / "probe_backend.py"
    )
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    backend.build_wheel(str(out))
    return out


@pytest.fixture(scope="session")
def sites(tmp_path_factory):
    """Real ``site-packages`` dirs, one per install route / modification."""
    base = tmp_path_factory.mktemp("clewdist")
    subprocess.run(
        [sys.executable, "-m", "venv", str(base / "venv")],
        check=True,
        capture_output=True,
        env=_env(base),
        timeout=300,
    )
    python = base / "venv" / ("Scripts" if os.name == "nt" else "bin") / "python"
    release = _project(base / "release", "VALUE = 1\n")
    patched = _project(base / "patched", "VALUE = 2  # local patch\n")
    wh_release = _wheelhouse(release, base / "wh_release")
    wh_patched = _wheelhouse(patched, base / "wh_patched")

    def install(label: str, *args: str) -> Path:
        site = base / label / "lib" / "site-packages"
        site.mkdir(parents=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-cache-dir"]
            + ["--disable-pip-version-check", "--target", str(site), *args],
            check=True,
            capture_output=True,
            env=_env(base),
            timeout=300,
        )
        return site

    out = {
        "release": install("release", "--find-links", str(wh_release), NAME),
        "patched": install("patched", "--find-links", str(wh_patched), NAME),
        "local_dir": install("local_dir", str(patched)),
        "edited": install("edited", "--find-links", str(wh_release), NAME),
    }
    time.sleep(0.01)
    (out["edited"] / NAME / "__init__.py").write_text("VALUE = 9\n")  # same size
    return out


def _dist(site: Path):
    found = [d for d in distributions(path=[str(site)]) if d.metadata["Name"] == NAME]
    if len(found) != 1:
        raise LookupError(f"expected one {NAME} in {site}, found {found}")
    return found[0]


def _recorded(site: Path, runs=("S1",)) -> dict:
    """Slice requirements whose provenance is the session's record of ``site``."""
    info = session_dp.distribution_provenance(_dist(site))
    return {"provenance": {NAME: [{**info, "runs": list(runs)}]}}


@pytest.fixture
def installed_here():
    """Make a site THIS interpreter's installation of the probe (undone after)."""
    added: list[str] = []

    def use(site: Path) -> None:
        sys.path.insert(0, str(site))
        added.append(str(site))

    yield use
    for entry in added:
        sys.path.remove(entry)


def _kinds(findings) -> list[str]:
    return sorted(f["kind"] for f in findings)


class TestFingerprintConformance:
    def test_clew_and_session_fingerprints_agree_on_installed_distributions(self):
        # Arrange: every RECORD-bearing distribution of the test environment
        dists = [d for d in distributions() if d.read_text("RECORD")][:200]
        # Act
        disagree = [
            d.metadata["Name"]
            for d in dists
            if record_fingerprint(d.read_text("RECORD"))
            != session_dp.record_fingerprint(d.read_text("RECORD"))
        ]
        # Assert
        assert (len(dists) > 10, disagree) == (True, [])

    def test_clew_and_session_detect_the_same_edited_files(self, sites, installed_here):
        # Arrange
        installed_here(sites["edited"])
        session_view = session_dp.distribution_provenance(_dist(sites["edited"]))
        # Act
        clew_view = current_distribution(NAME)
        # Assert
        assert (clew_view["modified_files"], clew_view["fingerprint"]) == (
            session_view["modified_files"],
            session_view["fingerprint"],
        )


class TestRecordedProvenance:
    def test_local_directory_install_is_not_from_index(self, sites):
        # Arrange
        requirements = _recorded(sites["local_dir"])
        # Act
        findings = environment_findings(requirements, check_current=False)
        # Assert
        assert _kinds(findings) == ["not_from_index"]

    def test_index_install_edited_in_place_is_flagged(self, sites):
        # Arrange
        requirements = _recorded(sites["edited"])
        # Act
        findings = environment_findings(requirements, check_current=False)
        # Assert
        assert _kinds(findings) == ["edited_after_install"]

    def test_intact_index_install_is_reproducible(self, sites):
        # Arrange
        requirements = _recorded(sites["release"])
        # Act
        findings = environment_findings(requirements, check_current=False)
        # Assert
        assert findings == []

    def test_message_names_the_local_source(self, sites):
        # Arrange
        requirements = _recorded(sites["local_dir"])
        # Act
        (finding,) = environment_findings(requirements, check_current=False)
        # Assert
        assert "local dir" in finding["message"]


class TestAgainstThisEnvironment:
    def test_patched_rebuild_recorded_release_installed_here_differs(
        self, sites, installed_here
    ):
        # Arrange: the E2 case — the run used a patched rebuild of 1.0.0,
        # this environment has the release 1.0.0
        requirements = _recorded(sites["patched"])
        installed_here(sites["release"])
        # Act
        findings = environment_findings(requirements, cache={})
        # Assert
        assert _kinds(findings) == ["content_differs"]

    def test_same_build_installed_here_is_reproducible(self, sites, installed_here):
        # Arrange
        requirements = _recorded(sites["release"])
        installed_here(sites["release"])
        # Act
        findings = environment_findings(requirements, cache={})
        # Assert
        assert findings == []

    def test_installation_edited_here_is_flagged(self, sites, installed_here):
        # Arrange
        requirements = _recorded(sites["release"])
        installed_here(sites["edited"])
        # Act
        findings = environment_findings(requirements, cache={})
        # Assert
        assert _kinds(findings) == ["edited_here"]

    def test_distribution_absent_here_is_not_a_content_finding(self, sites):
        # Arrange: nothing of the probe on sys.path
        requirements = _recorded(sites["patched"])
        # Act
        findings = environment_findings(requirements, cache={})
        # Assert
        assert findings == []


# ---------------------------------------------------------------------------
# Through the store: the session record -> slice -> clew verify
# ---------------------------------------------------------------------------


@pytest.fixture
def clew_project(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_tracker(None)
    project = tmp_path.resolve() / "proj"
    project.mkdir()
    (project / "script.py").write_text("print(1)\n")
    with project_root(project):
        yield project
    set_tracker(None)
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _claimed_run(project: Path, site: Path) -> Path:
    """A session run whose record is the real collector's view of ``site``;
    its output carries a registered claim."""
    from scitex_session._lifecycle._provenance import collect_run_metadata

    spec = importlib.util.spec_from_file_location(NAME, site / NAME / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(site))
    try:
        spec.loader.exec_module(module)
        meta = collect_run_metadata(
            str(project / "script.py"),
            modules={NAME: module},
            project_root=project,
        )
    finally:
        sys.path.remove(str(site))
    sid = f"env_{uuid.uuid4().hex[:10]}"
    on_session_start(sid, script_path=str(project / "script.py"), metadata=meta)
    out = project / "result.json"
    out.write_text(json.dumps({"value": 1}))
    get_tracker().record_output(out)
    on_session_close()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clew.add_claim(
            str(project / "paper.tex"), "value", 1, "1", source_file=str(out)
        )
    return out


class TestVerify:
    def test_slice_carries_the_recorded_provenance(self, clew_project, sites):
        # Arrange
        out = _claimed_run(clew_project, sites["local_dir"])
        # Act
        env = build_slice([out]).requirements()
        # Assert
        assert [e["source"] for e in env["provenance"][NAME]] == ["local_dir"]

    def test_default_verify_passes_with_a_warning(self, clew_project, sites):
        # Arrange
        _claimed_run(clew_project, sites["local_dir"])
        # Act
        result = clew.verify_all_claims(config=_empty_config(clew_project))
        # Assert
        assert (result.exit_code, result.warnings) == (0, ["ENV_NOT_REPRODUCIBLE"])

    def test_default_verify_lists_the_finding_on_the_claim(self, clew_project, sites):
        # Arrange
        _claimed_run(clew_project, sites["local_dir"])
        # Act
        result = clew.verify_all_claims(config=_empty_config(clew_project))
        # Assert
        assert _kinds(result.claims[0].environment) == ["not_from_index"]

    def test_strict_verify_fails_with_env_not_reproducible(self, clew_project, sites):
        # Arrange
        _claimed_run(clew_project, sites["local_dir"])
        # Act
        result = clew.verify_all_claims(strict=True, config=_empty_config(clew_project))
        # Assert
        assert (result.exit_code, result.exit_name) == (23, "ENV_NOT_REPRODUCIBLE")

    def test_strict_verify_respects_an_explicit_project_severity(
        self, clew_project, sites
    ):
        # Arrange: the project accepts local builds as policy
        _claimed_run(clew_project, sites["local_dir"])
        config = _empty_config(clew_project, "env_not_reproducible: warning\n")
        # Act
        result = clew.verify_all_claims(strict=True, config=config)
        # Assert
        assert result.exit_code == 0

    def test_reproducible_environment_verifies_without_warning(
        self, clew_project, sites
    ):
        # Arrange
        _claimed_run(clew_project, sites["release"])
        # Act
        result = clew.verify_all_claims(strict=True, config=_empty_config(clew_project))
        # Assert
        assert (result.exit_code, result.warnings) == (0, [])


def _empty_config(project: Path, severity: str = "") -> str:
    """An explicit clew config (so a user-level config cannot leak in)."""
    path = project / ".scitex" / "clew" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "verify:\n  severity:\n    " + severity if severity else "verify: {}\n"
    path.write_text(body)
    return str(path)


# EOF
