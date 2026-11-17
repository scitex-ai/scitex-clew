#!/usr/bin/env python3
"""Symlinks a run goes THROUGH to reach its files are recorded (#192).

A project holds a symlink (``alias -> data``, ``cfg.yaml -> /abs/config/..``,
``sub/config -> ../config``, a chain ``a -> b -> data``, a link to a shared
dataset outside the project) and the script opens its inputs through the link
path. The resolved file alone is not enough to re-run: the slice must carry
the link, a materialized slice must recreate it, and ``verify`` must check it.

Real project trees under ``tmp_path``, real ``os.symlink``, the real session
hooks and audit hook, a real PostgreSQL store, and a real re-execution of the
script from a materialized slice. No mocks.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from scitex_clew import _capture
from scitex_clew._capture import _external as _capture_external
from scitex_clew._chain._slice import build_slice
from scitex_clew._chain._types import VerificationStatus
from scitex_clew._chain._verify_ops import verify_run
from scitex_clew._db import get_db
from scitex_clew._links import link_entries, symlink_hops
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker

_ENVS = (_capture.ENV_VAR, _capture_external.ENV_EXTERNAL_INCLUDE)

#: The probe script: reads every path given on argv, writes their sizes.
_SCRIPT = """\
import json, sys
sizes = {p: len(open(p).read()) for p in sys.argv[2:]}
open(sys.argv[1], "w").write(json.dumps(sizes, sort_keys=True))
"""


@pytest.fixture(autouse=True)
def _clean_state():
    saved = {k: os.environ.pop(k, None) for k in _ENVS}
    set_tracker(None)
    _capture._ACTIVE = None
    yield
    set_tracker(None)
    _capture._ACTIVE = None
    for key, value in saved.items():
        os.environ.pop(key, None)
        if value is not None:
            os.environ[key] = value


@pytest.fixture
def project(tmp_path):
    root = (tmp_path / "proj").resolve()
    (root / "data").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "sub").mkdir()
    (root / "lib").mkdir()
    (root / "data" / "x.csv").write_text("a,b\n1,2\n")
    (root / "config" / "c.yaml").write_text("k: 1\n")
    (root / "lib" / "helper.py").write_text("VALUE = 41 + 1\n")
    (root / "run.py").write_text(_SCRIPT)
    return root


def _start(project):
    sid = f"link_{uuid.uuid4().hex[:12]}"
    on_session_start(
        sid,
        script_path=str(project / "run.py"),
        metadata={"project_root": str(project)},
    )
    return sid


def _read_all(paths):
    return {str(p): len(open(p).read()) for p in paths}


def _run(project, paths, out_name="out.json"):
    """One recorded run reading ``paths`` (as given) and writing an output."""
    sid = _start(project)
    out = project / out_name
    out.write_text(json.dumps(_read_all(paths), sort_keys=True))
    on_session_close()
    return sid, out


def _links(sid):
    meta = get_db().get_run(sid)["metadata"]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    return {e["link"]: e for e in meta.get("links", [])}


def _materialize(sl, project, dest):
    """Copy a slice's in-project files and recreate its links under ``dest``."""
    manifest = sl.to_dict()
    for item in manifest["files"]:
        path = Path(item["path"])
        if item["external"] or not path.is_relative_to(project):
            continue
        target = dest / path.relative_to(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, target)
    for link in manifest["links"]:
        where = dest / Path(link["link"]).relative_to(project)
        where.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link["recreate"], where)
    shutil.copy2(project / "run.py", dest / "run.py")
    return manifest


class TestSymlinkHops:
    def test_chain_yields_one_hop_per_link_in_order(self, project):
        # Arrange
        os.symlink("b", project / "a")
        os.symlink("data", project / "b")
        # Act
        hops = symlink_hops(str(project / "a" / "x.csv"))
        # Assert
        assert hops == [(str(project / "a"), "b"), (str(project / "b"), "data")]

    def test_dotdot_after_a_link_climbs_from_its_target(self, project):
        # Arrange: sub/deep -> ../data ; sub/deep/../config is <root>/config
        os.symlink("../data", project / "sub" / "deep")
        # Act
        entries = link_entries(
            str(project / "sub" / "deep" / ".." / "config" / "c.yaml"), str(project)
        )
        # Assert
        assert [e["files"] for e in entries] == [[str(project / "config" / "c.yaml")]]

    def test_link_outside_the_project_is_not_the_projects(self, project, tmp_path):
        # Arrange: the project itself reached through a link elsewhere
        os.symlink(project, tmp_path / "proj_alias")
        # Act
        entries = link_entries(
            str(tmp_path / "proj_alias" / "data" / "x.csv"), str(project)
        )
        # Assert
        assert entries == []


class TestLinksAreRecorded:
    def test_relative_dir_symlink(self, project):
        # Arrange
        os.symlink("data", project / "alias")
        # Act
        sid, _ = _run(project, [project / "alias" / "x.csv"])
        # Assert
        entry = _links(sid)[str(project / "alias")]
        assert (
            entry["target"],
            entry["recreate"],
            entry["in_project"],
            entry["kind"],
            entry["files"],
        ) == ("data", "data", True, "dir", [str(project / "data" / "x.csv")])

    def test_absolute_file_symlink_is_recreated_relative(self, project):
        # Arrange
        os.symlink(project / "config" / "c.yaml", project / "c.yaml")
        # Act
        sid, _ = _run(project, [project / "c.yaml"])
        # Assert
        entry = _links(sid)[str(project / "c.yaml")]
        assert (entry["target"], entry["recreate"], entry["kind"]) == (
            str(project / "config" / "c.yaml"),
            os.path.join("config", "c.yaml"),
            "file",
        )

    def test_symlinked_dir_opened_by_a_relative_path(self, project):
        # Arrange: sub/config -> ../config, opened as "config/c.yaml" from sub/
        os.symlink("../config", project / "sub" / "config")
        cwd = os.getcwd()
        os.chdir(project / "sub")
        # Act
        try:
            sid, _ = _run(project, ["config/c.yaml"])
        finally:
            os.chdir(cwd)
        # Assert
        assert _links(sid)[str(project / "sub" / "config")]["files"] == [
            str(project / "config" / "c.yaml")
        ]

    def test_chain_records_every_hop(self, project):
        # Arrange
        os.symlink("b", project / "a")
        os.symlink("data", project / "b")
        # Act
        sid, _ = _run(project, [project / "a" / "x.csv"])
        # Assert
        links = _links(sid)
        assert {k: v["recreate"] for k, v in links.items()} == {
            str(project / "a"): "b",
            str(project / "b"): "data",
        }

    def test_link_to_outside_is_recorded_with_its_resolved_target(
        self, project, tmp_path
    ):
        # Arrange: a shared dataset outside the project, opted in
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "raw.csv").write_text("r\n1\n")
        os.environ[_capture_external.ENV_EXTERNAL_INCLUDE] = str(shared)
        os.symlink(shared, project / "raw")
        # Act
        sid, _ = _run(project, [project / "raw" / "raw.csv"])
        # Assert
        entry = _links(sid)[str(project / "raw")]
        assert (entry["in_project"], entry["recreate"]) == (
            False,
            str(shared.resolve()),
        )

    def test_code_run_through_a_symlinked_dir(self, project):
        # Arrange
        os.symlink("lib", project / "libalias")
        sid = _start(project)
        # Act
        runpy.run_path(str(project / "libalias" / "helper.py"))
        (project / "out.json").write_text("{}")
        on_session_close()
        # Assert
        assert _links(sid)[str(project / "libalias")]["files"] == [
            str(project / "lib" / "helper.py")
        ]

    def test_explicitly_recorded_input_through_a_link(self, project):
        # Arrange: what the stx.io.load hook calls
        os.symlink("data", project / "alias")
        sid = _start(project)
        # Act
        get_tracker().record_input(project / "alias" / "x.csv")
        on_session_close()
        # Assert
        assert str(project / "alias") in _links(sid)

    def test_a_link_reaching_only_an_unrecorded_file_is_not_stored(self, project):
        # Arrange: the run writes through the link and reads it back (an
        # intermediate it then deletes) — not a dependency
        os.symlink("data", project / "alias")
        sid = _start(project)
        # Act
        tmp = project / "alias" / "scratch.txt"
        tmp.write_text("t")
        tmp.read_text()
        tmp.unlink()
        on_session_close()
        # Assert
        assert _links(sid) == {}


class TestSliceCarriesLinks:
    def test_slice_lists_the_link_to_recreate(self, project):
        # Arrange
        os.symlink("data", project / "alias")
        _, out = _run(project, [project / "alias" / "x.csv"])
        # Act
        links = build_slice([out]).to_dict()["links"]
        # Assert
        assert [(e["link"], e["recreate"]) for e in links] == [
            (str(project / "alias"), "data")
        ]

    def test_external_target_is_required_not_bundled_and_its_link_listed(
        self, project, tmp_path
    ):
        # Arrange
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "raw.csv").write_text("r\n1\n")
        os.environ[_capture_external.ENV_EXTERNAL_INCLUDE] = str(shared)
        os.symlink(shared, project / "raw")
        _, out = _run(project, [project / "raw" / "raw.csv"])
        # Act
        manifest = build_slice([out]).to_dict()
        # Assert
        required = manifest["required_not_bundled"]
        assert (
            [(r["path"], r["links"]) for r in required],
            [e["link"] for e in manifest["links"]],
        ) == (
            [(str((shared / "raw.csv").resolve()), [str(project / "raw")])],
            [str(project / "raw")],
        )

    @pytest.mark.parametrize(
        "links, used",
        [
            pytest.param([("alias", "data")], "alias/x.csv", id="relative-dir"),
            pytest.param([("c.yaml", "@config/c.yaml")], "c.yaml", id="absolute"),
            pytest.param(
                [("sub/config", "../config")], "sub/config/c.yaml", id="subdir"
            ),
            pytest.param([("a", "b"), ("b", "data")], "a/x.csv", id="chain"),
        ],
    )
    def test_script_reruns_from_a_materialized_slice(
        self, project, tmp_path, links, used
    ):
        # Arrange: "@" marks an absolute target inside the project
        for link, target in links:
            text = str(project / target[1:]) if target.startswith("@") else target
            os.symlink(text, project / link)
        used = [used]
        cwd = os.getcwd()
        os.chdir(project)
        try:
            _, out = _run(project, used)
        finally:
            os.chdir(cwd)
        dest = tmp_path / "materialized"
        dest.mkdir()
        _materialize(build_slice([out]), project, dest)
        # Act: re-execute the script from the slice alone
        proc = subprocess.run(
            [sys.executable, "run.py", "rerun.json", *used],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Assert
        assert (proc.returncode, proc.stderr) == (0, "")


class TestVerifyChecksLinks:
    def test_unchanged_link_verifies(self, project):
        # Arrange
        os.symlink("data", project / "alias")
        sid, _ = _run(project, [project / "alias" / "x.csv"])
        # Act
        result = verify_run(sid)
        # Assert
        assert (result.status, [f.path for f in result.files if f.link]) == (
            VerificationStatus.VERIFIED,
            [str(project / "alias")],
        )

    def test_retargeted_link_fails_even_when_bytes_match(self, project):
        # Arrange: a second dir with identical bytes; the link now points there
        os.symlink("data", project / "alias")
        sid, _ = _run(project, [project / "alias" / "x.csv"])
        shutil.copytree(project / "data", project / "data2")
        os.unlink(project / "alias")
        os.symlink("data2", project / "alias")
        # Act
        result = verify_run(sid)
        # Assert
        link = next(f for f in result.files if f.link)
        assert (link.status, result.is_verified) == (VerificationStatus.MISMATCH, False)

    def test_removed_link_is_missing(self, project):
        # Arrange
        os.symlink("data", project / "alias")
        sid, _ = _run(project, [project / "alias" / "x.csv"])
        os.unlink(project / "alias")
        # Act
        result = verify_run(sid)
        # Assert
        link = next(f for f in result.files if f.link)
        assert (link.status, result.is_verified) == (VerificationStatus.MISSING, False)

    def test_changed_target_bytes_still_fail_through_the_file_row(self, project):
        # Arrange
        os.symlink("data", project / "alias")
        sid, _ = _run(project, [project / "alias" / "x.csv"])
        (project / "data" / "x.csv").write_text("changed\n")
        # Act
        result = verify_run(sid)
        # Assert
        target = next(
            f for f in result.files if f.path == str(project / "data" / "x.csv")
        )
        assert target.status == VerificationStatus.MISMATCH


# EOF
