"""Store-free re-execution of a REAL bundle, offline.

The recorded runs are re-executed for real (child interpreters) from the
bundle's argv/cwd in a temporary copy of the project; no network, no mocks.
"""

from __future__ import annotations

import os
import shutil

import pytest
from scitex_clew._exchange import rerun_bundle, schema_errors

BUNDLE = ".scitex/clew/evidence-bundle.json"


def _tree_state(root):
    """``{relative path: (size, mtime_ns)}`` of every file under ``root``."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            out[os.path.relpath(path, root)] = (st.st_size, st.st_mtime_ns)
    return out


def _store_run_ids(root):
    from scitex_clew._db import get_db
    from scitex_clew._db._paths import project_root

    with project_root(root):
        return sorted(r["session_id"] for r in get_db().list_runs(limit=10_000))


@pytest.fixture(scope="module")
def rerun(signed_bundle, bundle_project):
    """``(report, tree before, tree after, store runs before, after)``."""
    tree_before, runs_before = (
        _tree_state(bundle_project),
        _store_run_ids(bundle_project),
    )
    report = rerun_bundle(signed_bundle, bundle_project, timeout=900)
    return (report, tree_before, _tree_state(bundle_project), runs_before,
            _store_run_ids(bundle_project))  # fmt: skip


@pytest.fixture(scope="module")
def changed(signed_bundle, bundle_project, tmp_path_factory):
    """The rerun report of a copy whose stats script now computes something else."""
    root = _copy_with_changed_stats(bundle_project, tmp_path_factory.mktemp("changed"))
    return rerun_bundle(root / BUNDLE, root, timeout=900)


def _copy_with_changed_stats(project, dest):
    """A private copy of ``project`` whose stats script adds 1 to the mean."""
    root = dest / project.name
    shutil.copytree(project, root, symlinks=True)
    script = root / "scripts" / "stats.py"
    script.write_text(
        script.read_text().replace('df["x"].mean()', 'df["x"].mean() + 1')
    )
    return root


@pytest.fixture(scope="module")
def kept(signed_bundle, bundle_project, tmp_path_factory):
    """``(report, work dir)`` of a rerun whose work directory is KEPT."""
    work = tmp_path_factory.mktemp("kept") / "work"
    return rerun_bundle(signed_bundle, bundle_project, timeout=900, work_dir=work), work


def _by_id(items, key):
    return {item[key]: item for item in items}


def test_report_validates_against_its_shipped_schema(rerun):
    # Arrange
    report = rerun[0]
    # Act
    errors = schema_errors(report, "rerun-report")
    # Assert
    assert errors == []


def test_every_run_reproduces(rerun):
    # Arrange
    report = rerun[0]
    # Act
    statuses = [r["status"] for r in report["runs"]]
    # Assert
    assert statuses == ["reproduced", "reproduced"], report["runs"]


def test_bundle_is_executable(rerun):
    # Arrange
    report = rerun[0]
    # Act
    executable = report["executable"]
    # Assert
    assert executable is True


def test_every_claim_value_is_recomputed(rerun):
    # Arrange
    report = rerun[0]
    # Act
    statuses = {c["claim_id"]: c["status"] for c in report["claims"]}
    # Assert
    assert statuses == {
        "n_rows": "reproduced",
        "mean_x": "reproduced",
        "double": "reproduced",
    }


def test_recomputed_value_and_tolerance_are_reported(rerun):
    # Arrange
    claim = _by_id(rerun[0]["claims"], "claim_id")["mean_x"]
    # Act
    got = (claim["recomputed_value"], claim["tolerance"]["basis"])
    # Assert
    assert got == (2.0, "implied")


def test_rerun_writes_nothing_into_the_project_root(rerun):
    # Arrange
    _report, before, after, _rb, _ra = rerun
    # Act
    changed_files = {
        p for p in set(before) | set(after) if before.get(p) != after.get(p)
    }
    # Assert
    assert changed_files == set()


def test_rerun_records_nothing_in_the_store(rerun):
    # Arrange
    _report, _b, _a, runs_before, runs_after = rerun
    # Act
    same = runs_before == runs_after
    # Assert
    assert same


def test_bundle_hash_names_the_bundle_file(rerun, signed_bundle):
    # Arrange
    from scitex_clew._exchange import sha256_file

    expected = sha256_file(signed_bundle)
    # Act
    got = rerun[0]["bundle_sha256"]
    # Assert
    assert got == expected


def test_default_rerun_keeps_no_work_dir(rerun):
    # Arrange
    report = rerun[0]
    # Act
    work_dir = report["work_dir"]
    # Assert
    assert work_dir is None


def test_kept_work_dir_is_reported_absolute(kept):
    # Arrange
    report, work = kept
    # Act
    reported = report["work_dir"]
    # Assert
    assert reported == str(work.resolve())


def test_kept_work_dir_still_holds_the_replayed_tree(kept):
    # Arrange
    _report, work = kept
    # Act
    present = (work / "bundle-project" / "scripts" / "stats.py").is_file()
    # Assert
    assert present


def test_kept_rerun_reproduces(kept):
    # Arrange
    report = kept[0]
    # Act
    statuses = [r["status"] for r in report["runs"]]
    # Assert
    assert statuses == ["reproduced", "reproduced"]


def test_every_reported_run_dir_exists(kept):
    # Arrange
    report, work = kept
    # Act
    missing = [
        r["run_dir"] for r in report["runs"] if not (work / r["run_dir"]).is_dir()
    ]
    # Assert
    assert missing == []


def test_hashing_resolved_paths_gives_the_reported_sha256(kept):
    # Arrange
    from scitex_clew._exchange import sha256_file

    report, work = kept
    outputs = [o for r in report["runs"] for o in r["outputs"]]
    # Act
    rehashed = [sha256_file(work / o["resolved_path"]) for o in outputs]
    # Assert
    assert rehashed == [o["actual_sha256"] for o in outputs]


def test_non_empty_work_dir_is_refused(signed_bundle, bundle_project, tmp_path):
    # Arrange
    (tmp_path / "leftover.txt").write_text("x")

    # Act
    def act():
        rerun_bundle(signed_bundle, bundle_project, work_dir=tmp_path)

    # Assert
    with pytest.raises(FileExistsError):
        act()


def test_changed_script_output_differs(changed, signed_bundle):
    # Arrange
    from scitex_clew._exchange import load_bundle

    doc = load_bundle(signed_bundle)[0]
    stats_id = next(
        r["run_id"] for r in doc["runs"] if r["script"] == "scripts/stats.py"
    )
    # Act
    status = _by_id(changed["runs"], "run_id")[stats_id]["status"]
    # Assert
    assert status == "differs"


def test_changed_script_makes_its_claim_differ(changed):
    # Arrange
    claims = _by_id(changed["claims"], "claim_id")
    # Act
    got = (claims["mean_x"]["status"], claims["mean_x"]["recomputed_value"])
    # Assert
    assert got == ("differs", 3.0)


def test_changed_script_leaves_untouched_values_reproduced(changed):
    # Arrange
    claims = _by_id(changed["claims"], "claim_id")
    # Act
    status = claims["n_rows"]["status"]
    # Assert
    assert status == "reproduced"


def test_failing_script_is_failed_and_its_consumer_skipped(
    signed_bundle, bundle_project, tmp_path
):
    # Arrange
    root = tmp_path / bundle_project.name
    shutil.copytree(bundle_project, root, symlinks=True)
    (root / "scripts" / "stats.py").write_text("raise SystemExit(3)\n")
    # Act
    report = rerun_bundle(root / BUNDLE, root, timeout=900)
    # Assert
    assert [(r["status"], r["exit_code"]) for r in report["runs"]] == [
        ("failed", 3),
        ("skipped", None),
    ]


# EOF
