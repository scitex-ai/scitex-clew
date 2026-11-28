"""Which tree `clew bundle verify / rerun / export` checks — with REAL git worktrees.

Regression for a false OK: a STALE bundle committed in a linked worktree was
verified from the MAIN checkout's working directory (``clew bundle verify
<worktree>/.scitex/clew/evidence-bundle.json``, no ``--project-root``). The
root defaulted to ``.``, so the main checkout's files — still the OLD ones
the stale bundle pinned — were hashed, and the command printed ``[OK] 69/69``.

Every repository here is real (``git init`` + ``git worktree add``); the CLI
is the real ``python -m scitex_clew`` in a child process started IN the
directory under test (the working directory is the variable). No mocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scitex_clew._exchange import bundle_home, sha256_file, write_bundle

BUNDLE = Path(".scitex/clew/evidence-bundle.json")


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _bundle_for(root: Path) -> dict:
    """A schema-valid, unsigned bundle pinning ``root``'s CURRENT files."""
    return {
        "schema": "scitex-clew.evidence-bundle",
        "schema_version": "1.0.0",
        "exported_at": "2026-11-28T00:00:00+00:00",
        "clew_version": "test",
        "project": {"project_id": "clew-test", "root_name": root.name},
        "runs": [{
            "run_id": "R1", "script": "run.py", "argv": ["run.py"],
            "interpreter": {"name": "python", "version": "3.12"}, "cwd": ".",
            "inputs": {},
            "outputs": {"out/r.json": sha256_file(root / "out" / "r.json")},
            "external_inputs": [], "status": "success",
            "started_at": "2026-11-28T00:00:00", "finished_at": "2026-11-28T00:00:01",
        }],
        "edges": [],
        "claims": [],
    }  # fmt: skip


@pytest.fixture
def checkouts(tmp_path):
    """``(main, worktree)``: the worktree regenerated ``out/r.json`` but kept the
    OLD bundle (stale); the main checkout still holds the OLD output."""
    main_root = tmp_path / "repo"
    (main_root / "out").mkdir(parents=True)
    (main_root / "run.py").write_text("print('hi')\n")
    (main_root / "out" / "r.json").write_text('{"n": 1}\n')
    write_bundle(_bundle_for(main_root), main_root / BUNDLE)
    _git(main_root, "init", "-q", "-b", "main")
    _git(main_root, "add", "-A")
    _git(main_root, "commit", "-q", "-m", "init")
    wt = main_root / ".worktrees" / "topic"
    _git(main_root, "worktree", "add", "-q", "-b", "topic", str(wt))
    (wt / "out" / "r.json").write_text('{"n": 2}\n')
    _git(wt, "commit", "-q", "-am", "regenerate without re-exporting the bundle")
    return main_root.resolve(), wt.resolve()


class _Result:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.exit_code = proc.returncode
        self.stdout = proc.stdout
        self.output = proc.stdout + proc.stderr


def _invoke(cwd: Path, *args: str) -> _Result:
    """Run the real CLI from ``cwd`` (no session-root override inherited)."""
    env = {k: v for k, v in os.environ.items() if k != "SCITEX_SESSION_PROJECT_ROOT"}
    proc = subprocess.run(
        [sys.executable, "-m", "scitex_clew", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    return _Result(proc)


def _json(result: _Result) -> dict:
    return json.loads(result.stdout)


@pytest.fixture
def outside_dir(tmp_path) -> Path:
    """A directory in no work tree (skipped where the temp dir is inside one)."""
    path = tmp_path / "downloads"
    path.mkdir()
    if bundle_home(path / "b.json") is not None:
        pytest.skip("the temp dir is inside a git work tree on this host")
    return path


def test_worktree_bundle_from_main_checkout_is_refused_not_ok(checkouts):
    # Arrange — the exact false-OK invocation
    main_root, wt = checkouts
    # Act
    result = _invoke(main_root, "bundle", "verify", str(wt / BUNDLE))
    # Assert
    assert (result.exit_code, "ambiguous project root" in result.output) == (2, True)


def test_ambiguity_error_names_both_trees(checkouts):
    # Arrange
    main_root, wt = checkouts
    # Act
    out = _invoke(main_root, "bundle", "verify", str(wt / BUNDLE)).output
    # Assert
    assert (str(wt) in out, str(main_root) in out) == (True, True)


def test_stale_bundle_fails_from_inside_the_worktree(checkouts):
    # Arrange
    _main_root, wt = checkouts
    # Act
    result = _invoke(wt, "bundle", "verify", str(BUNDLE), "--json")
    # Assert
    payload = _json(result)
    assert (result.exit_code, payload["project_root"], len(payload["files"]["mismatched"])) == (
        1,
        str(wt),
        1,
    )


def test_stale_bundle_fails_from_a_worktree_subdirectory(checkouts):
    # Arrange
    _main_root, wt = checkouts
    # Act
    result = _invoke(wt / "out", "bundle", "verify", str(wt / BUNDLE), "--json")
    # Assert
    payload = _json(result)
    assert (
        result.exit_code,
        payload["project_root"],
        len(payload["files"]["mismatched"]),
    ) == (
        1,
        str(wt),
        1,
    )


def test_text_output_prints_the_tree_it_verified(checkouts):
    # Arrange
    _main_root, wt = checkouts
    # Act
    out = _invoke(wt, "bundle", "verify", str(BUNDLE)).output
    # Assert
    assert f"project root: {wt} (bundle_location)" in out


def test_explicit_root_is_honoured_and_the_mismatch_is_shown(checkouts):
    # Arrange — explicitly checking the worktree's bundle against main's tree
    main_root, wt = checkouts
    args = ("bundle", "verify", str(wt / BUNDLE), "--project-root", str(main_root))
    # Act
    result = _invoke(main_root, *args)
    # Assert
    assert (
        result.exit_code,
        f"NOTE the bundle itself lives in {wt}" in result.output,
    ) == (
        0,
        True,
    )


def test_bundle_outside_dot_scitex_resolves_to_its_git_worktree(checkouts):
    # Arrange — a bundle kept elsewhere in the worktree, verified from main
    main_root, wt = checkouts
    loose = wt / "evidence" / "b.json"
    loose.parent.mkdir()
    loose.write_bytes((wt / BUNDLE).read_bytes())
    # Act
    result = _invoke(main_root, "bundle", "verify", str(loose))
    # Assert
    assert (result.exit_code, "(bundle_git)" in result.output) == (2, True)


def test_bundle_home_of_a_linked_worktree_is_the_worktree_not_the_common_dir(checkouts):
    # Arrange
    _main_root, wt = checkouts
    loose = wt / "b.json"
    loose.write_text("{}")
    # Act
    home = bundle_home(loose)
    # Assert
    assert home == (wt, "bundle_git")


def test_bundle_with_no_project_uses_the_working_directorys_tree(
    checkouts, outside_dir
):
    # Arrange — a downloaded bundle file outside every repository
    _main_root, wt = checkouts
    outside = outside_dir / "b.json"
    outside.write_bytes((wt / BUNDLE).read_bytes())
    # Act
    result = _invoke(wt, "bundle", "verify", str(outside), "--json")
    # Assert
    payload = _json(result)
    assert (
        result.exit_code,
        payload["project_root"],
        payload["project_root_source"],
    ) == (
        1,
        str(wt),
        "cwd:git",
    )


def test_rerun_of_a_worktree_bundle_from_main_checkout_is_refused(checkouts):
    # Arrange
    main_root, wt = checkouts
    # Act
    result = _invoke(main_root, "bundle", "rerun", str(wt / BUNDLE), "--dry-run")
    # Assert
    assert result.exit_code == 2


def test_rerun_dry_run_names_the_tree_it_would_replay(checkouts):
    # Arrange
    _main_root, wt = checkouts
    # Act
    result = _invoke(wt, "bundle", "rerun", str(BUNDLE), "--dry-run", "--json")
    # Assert
    assert _json(result)["project_root"] == str(wt)


def test_export_into_another_worktree_is_refused(checkouts):
    # Arrange — main's records would be written as the worktree's bundle
    main_root, wt = checkouts
    args = ("bundle", "export", "--out", str(wt / BUNDLE), "--dry-run")
    # Act
    result = _invoke(main_root, *args)
    # Assert
    assert result.exit_code == 2


def test_export_from_a_worktree_subdirectory_targets_the_worktree(checkouts):
    # Arrange
    _main_root, wt = checkouts
    # Act
    result = _invoke(wt / "out", "bundle", "export", "--dry-run", "--json")
    # Assert
    payload = _json(result)
    assert (payload["project_root"], payload["out"]) == (str(wt), str(wt / BUNDLE))


# EOF
