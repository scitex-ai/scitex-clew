#!/usr/bin/env python3
"""Project-root detection — conformance with scitex-session, and where it lands.

``tests/scitex_clew/conformance/project-root-vectors.json`` is byte-identical in
scitex-session, whose suite runs the same vectors against ITS resolver. Both
passing is what keeps "which directory is the project" one concept.

Real directory trees, real ``git init``, real ``$HOME`` / env / cwd, a real
PostgreSQL store (autouse ``isolated_store``). No mocks.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from scitex_clew._core._config import load_config
from scitex_clew._core._project_root import PROJECT_ROOT_ENV, resolve_project_root
from scitex_clew._db import reset_db
from scitex_clew._db._paths import (
    clear_session_project_root,
    project_root,
    project_root_info,
    set_session_project_root,
)
from scitex_clew._db._scope import resolve_project_scope

VECTORS = (
    Path(__file__).resolve().parents[1] / "conformance" / "project-root-vectors.json"
)
CASES = json.loads(VECTORS.read_text())["cases"]
GIT = shutil.which("git")


@contextlib.contextmanager
def _process(home: Path, cwd: Path, env_root: str | None = None) -> Iterator:
    """Real process state: ``$HOME``, ``$SCITEX_SESSION_PROJECT_ROOT``, cwd."""
    keys = ("HOME", PROJECT_ROOT_ENV, "SCITEX_CLEW_PROJECT")
    saved = {k: os.environ.get(k) for k in keys}
    saved_cwd = os.getcwd()
    os.environ["HOME"] = str(home)
    os.environ.pop("SCITEX_CLEW_PROJECT", None)
    if env_root is None:
        os.environ.pop(PROJECT_ROOT_ENV, None)
    else:
        os.environ[PROJECT_ROOT_ENV] = env_root
    os.chdir(cwd)
    try:
        yield
    finally:
        os.chdir(saved_cwd)
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _build(sandbox: Path, case: dict) -> None:
    for entry in case.get("tree", []):
        path = sandbox / entry
        if entry.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
    for repo in case.get("git_init", []):
        subprocess.run([GIT, "-C", str(sandbox / repo), "init", "-q"], check=True)


def _abs(sandbox: Path, rel: str | None) -> str | None:
    return None if rel is None else str(sandbox / rel)


RESOLVING = [c for c in CASES if "error" not in c["expect"]]
FAILING = [c for c in CASES if "error" in c["expect"]]


@contextlib.contextmanager
def _vector(case: dict, tmp_path: Path) -> Iterator[dict]:
    """Build the case's sandbox and enter its process state."""
    if case.get("git_init") and GIT is None:
        pytest.skip("git executable not on PATH")
    sandbox = tmp_path.resolve()
    _build(sandbox, case)
    with _process(
        sandbox / case.get("home", "."),
        sandbox / case.get("cwd", "."),
        _abs(sandbox, case.get("env")),
    ):
        yield {
            "sandbox": sandbox,
            "script": _abs(sandbox, case.get("script")),
            "explicit": _abs(sandbox, case.get("explicit")),
        }


class TestConformanceVectors:
    """The shared table, run against clew's resolver."""

    @pytest.mark.parametrize("case", RESOLVING, ids=[c["id"] for c in RESOLVING])
    def test_vector_resolves_expected_root_rule_and_warning(
        self, case, tmp_path, caplog
    ):
        # Arrange
        expect = case["expect"]
        # Act
        with _vector(case, tmp_path) as v, caplog.at_level(logging.WARNING):
            got = resolve_project_root(v["script"], explicit=v["explicit"])
        # Assert
        assert (
            got["project_root"],
            got["project_root_source"],
            got["project_root_marker"],
            "no project root found" in caplog.text,
        ) == (
            str((v["sandbox"] / expect["root"]).resolve()),
            expect["source"],
            expect["marker"],
            bool(case.get("warns")),
        )

    @pytest.mark.parametrize("case", FAILING, ids=[c["id"] for c in FAILING])
    def test_vector_with_a_bad_explicit_root_raises_value_error(self, case, tmp_path):
        # Arrange
        resolve = resolve_project_root
        # Act
        with _vector(case, tmp_path) as v:
            call = lambda: resolve(v["script"], explicit=v["explicit"])
            # Assert
            with pytest.raises(ValueError, match="is not an existing directory"):
                call()


def _research_project(root: Path) -> Path:
    """Non-VCS SciTeX research layout; returns its scripts/ dir."""
    for sub in ("config", "data", "scripts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root / "scripts"


class TestStandaloneScopeAndConfig:
    """The bug: a non-git project used from scripts/ scoped itself to scripts/."""

    def test_project_id_is_minted_at_the_project_root_not_scripts(self, tmp_path):
        # Arrange
        scripts = _research_project(tmp_path.resolve() / "proj")
        # Act
        with _process(tmp_path.resolve(), scripts):
            resolve_project_scope()
        # Assert
        assert (
            (scripts.parent / ".scitex" / "clew" / "project-id").is_file(),
            (scripts / ".scitex").exists(),
        ) == (True, False)

    def test_config_scope_of_a_non_git_project_is_found_from_scripts(self, tmp_path):
        # Arrange
        scripts = _research_project(tmp_path.resolve() / "proj")
        cfg_dir = scripts.parent / ".scitex" / "clew"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text("verify:\n  severity: strict\n")
        # Act
        with _process(tmp_path.resolve(), scripts):
            cfg = load_config()
        # Assert
        assert cfg.get("verify", {}).get("severity") == "strict"

    def test_info_records_the_rule(self, tmp_path):
        # Arrange
        scripts = _research_project(tmp_path.resolve() / "proj")
        # Act
        with _process(tmp_path.resolve(), scripts):
            info = project_root_info()
        # Assert
        assert (
            info["project_root_source"],
            info["project_root_marker"],
            info["via"],
        ) == (
            "marker",
            "scripts/ + config/",
            "detected",
        )

    def test_explicit_block_wins_and_is_reported_as_argument(self, tmp_path):
        # Arrange
        scripts = _research_project(tmp_path.resolve() / "proj")
        # Act
        with _process(tmp_path.resolve(), scripts), project_root(scripts):
            info = project_root_info()
        # Assert
        assert (info["project_root"], info["via"]) == (str(scripts), "argument")


class TestSessionRootIsTheSourceOfTruth:
    def test_session_metadata_root_wins_over_detection(self, tmp_path):
        # Arrange: cwd detection would say scripts/'s project; session says other
        base = tmp_path.resolve()
        scripts = _research_project(base / "proj")
        other = base / "other"
        other.mkdir()
        meta = {"project_root": str(other), "project_root_source": "env"}
        # Act
        with _process(base, scripts):
            set_session_project_root(meta)
            try:
                info = project_root_info()
            finally:
                clear_session_project_root()
        # Assert
        assert (info["project_root"], info["project_root_source"], info["via"]) == (
            str(other),
            "env",
            "session",
        )

    def test_older_session_without_a_root_uses_the_same_rule_from_the_script(
        self, tmp_path
    ):
        # Arrange
        base = tmp_path.resolve()
        scripts = _research_project(base / "proj")
        script = scripts / "run.py"
        script.write_text("")
        # Act
        with _process(base, base):
            set_session_project_root({"cwd": str(base)}, str(script))
            try:
                info = project_root_info()
            finally:
                clear_session_project_root()
        # Assert
        assert (info["project_root"], info["project_root_source"]) == (
            str(base / "proj"),
            "marker",
        )


class TestLegacyStoreMigration:
    """An id older clew minted in scripts/ — warned, adopted, never moved."""

    def _legacy(self, tmp_path) -> tuple[Path, Path]:
        scripts = _research_project(tmp_path.resolve() / "proj")
        legacy = scripts / ".scitex" / "clew" / "project-id"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("clew-legacyid\n")
        return scripts, legacy

    def test_legacy_id_is_kept_so_history_is_not_split(self, tmp_path):
        # Arrange
        scripts, _ = self._legacy(tmp_path)
        # Act
        with _process(tmp_path.resolve(), scripts):
            scope = resolve_project_scope()
        # Assert
        assert scope == "clew-legacyid"

    def test_nothing_is_moved_or_minted(self, tmp_path):
        # Arrange
        scripts, legacy = self._legacy(tmp_path)
        # Act
        with _process(tmp_path.resolve(), scripts):
            resolve_project_scope()
        # Assert
        assert (legacy.is_file(), (scripts.parent / ".scitex").exists()) == (
            True,
            False,
        )

    def test_warning_carries_a_move_command_that_works(self, tmp_path, caplog):
        # Arrange
        scripts, legacy = self._legacy(tmp_path)
        from scitex_clew._db import _scope

        _scope._warned.clear()
        # Act
        with _process(tmp_path.resolve(), scripts):
            with caplog.at_level(logging.WARNING):
                resolve_project_scope()
        command = caplog.text.split("Move it:")[1].strip().splitlines()[0].strip()
        subprocess.run(["bash", "-c", command], check=True)
        with _process(tmp_path.resolve(), scripts):
            reset_db()
            moved_scope = resolve_project_scope()
        # Assert
        assert (legacy.exists(), moved_scope) == (False, "clew-legacyid")

    def test_id_of_an_unrelated_cwd_project_is_never_adopted(self, tmp_path):
        # Arrange: a session for proj/ started from another project's dir,
        # which holds that OTHER project's id.
        base = tmp_path.resolve()
        _research_project(base / "proj")
        other = base / "other"
        (other / ".scitex" / "clew").mkdir(parents=True)
        (other / "pyproject.toml").write_text("")
        (other / ".scitex" / "clew" / "project-id").write_text("clew-otherid\n")
        # Act
        with _process(base, other):
            set_session_project_root({"project_root": str(base / "proj")})
            try:
                scope = resolve_project_scope()
            finally:
                clear_session_project_root()
        # Assert
        assert scope != "clew-otherid"

    def test_two_ids_are_reported_as_a_split(self, tmp_path, caplog):
        # Arrange
        scripts, _ = self._legacy(tmp_path)
        new = scripts.parent / ".scitex" / "clew" / "project-id"
        new.parent.mkdir(parents=True)
        new.write_text("clew-newid\n")
        from scitex_clew._db import _scope

        _scope._warned.clear()
        # Act
        with _process(tmp_path.resolve(), scripts):
            with caplog.at_level(logging.WARNING):
                scope = resolve_project_scope()
        # Assert
        assert (scope, "TWO provenance ids" in caplog.text) == ("clew-newid", True)


# EOF
