#!/usr/bin/env python3
"""Per-run METADATA records a slice carries: environment, symlinks, script.

Split out of :mod:`._slice` (512-line limit). Both come from the kept runs'
recorded metadata rather than from ``file_hashes`` rows:

* ``packages`` / ``unresolved_imports`` (scitex-session >= 0.3.6) — what a
  re-run must install — and ``package_provenance`` (>= 0.5.0): how each was
  installed and a fingerprint of its content;
* ``links`` (#192, :mod:`scitex_clew._links`) — the in-project symlinks the run
  went through to reach its files. A slice keeps a link when it reaches a
  kept file; materializing the slice must recreate it, or a re-run that opens
  the link path finds nothing;
* ``script_path`` / ``script_hash`` — the run's EXECUTABLE, the middle of the
  input -> executable -> output triplet. It is a run attribute, not a file
  node, so it changes no slice count (a notebook run's code files are the
  exception: :func:`collect_recipes` adds them as files).
"""

from __future__ import annotations

import json
from pathlib import PurePath

__all__ = [
    "collect_links",
    "describe_script",
    "run_environment",
    "run_links",
    "run_metadata_of",
    "run_script",
]


def _run_metadata(db, sid: str) -> dict | None:
    """Run ``sid``'s metadata as a dict (None when unreadable)."""
    raw = (db.get_run(sid) or {}).get("metadata")
    try:
        meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return None
    return meta if isinstance(meta, dict) else None


def run_metadata_of(run: dict | None) -> dict:
    """A run row's metadata as a dict (``{}`` when absent or unreadable)."""
    raw = (run or {}).get("metadata")
    try:
        meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return {}
    return meta if isinstance(meta, dict) else {}


def run_environment(db, sid: str) -> dict | None:
    """``{"packages", "unresolved_imports", "package_provenance"}`` of run ``sid``."""
    meta = _run_metadata(db, sid)
    if meta is None or "packages" not in meta:
        return None
    packages = meta.get("packages")
    provenance = meta.get("package_provenance")
    return {
        "packages": dict(packages) if isinstance(packages, dict) else None,
        "unresolved_imports": dict(meta.get("unresolved_imports") or {}),
        # None = not recorded (scitex-session < 0.5.0), never "all fine"
        "package_provenance": (
            dict(provenance) if isinstance(provenance, dict) else None
        ),
    }


def run_script(db, sid: str) -> dict | None:
    """``{"path", "hash", "project_root"}`` of the script run ``sid`` executed.

    ``project_root`` is the run's own recorded root (scitex-session's
    ``project_root``, else the ``clew_project_root`` the tracker recorded),
    None when neither was recorded. Returns None when the run has no script.
    """
    run = db.get_run(sid) or {}
    path = run.get("script_path")
    if not path:
        return None
    meta = run_metadata_of(run)
    clew_root = meta.get("clew_project_root")
    root = meta.get("project_root") or (
        clew_root.get("project_root") if isinstance(clew_root, dict) else None
    )
    return {
        "path": str(path),
        "hash": run.get("script_hash"),
        "project_root": str(root) if root else None,
    }


def describe_script(entry: dict | None) -> str:
    """``script: <path> (sha256 <12 hex>)`` for the text view of a slice.

    The path is project-relative when it lies inside the run's project root,
    absolute otherwise. A hash with a scheme prefix (a notebook's
    ``ipynb-code-v1:<hex>``) is labelled by that scheme.
    """
    if not entry:
        return "script: not recorded"
    path = PurePath(entry["path"])
    root = entry.get("project_root")
    if root and path.is_absolute() and path.is_relative_to(root):
        path = path.relative_to(root)
    digest = entry.get("hash")
    if not digest:
        return f"script: {path} (hash not recorded)"
    scheme, _, hexpart = str(digest).rpartition(":")
    return f"script: {path} ({scheme or 'sha256'} {hexpart[:12]})"


def collect_recipes(db, runs, input_hashes=None, files=None) -> dict[str, dict]:
    """``{sid: recipe}`` for every kept run that a notebook ran.

    A notebook run is re-executed by running the notebook (headless, top to
    bottom; :func:`scitex_clew._chain._notebook.rerun_recipe`), never by replaying
    the kernel's argv. Runs without a recipe replay their recorded argv.

    With ``files`` (the slice's ``{path: hash}``), the code each recipe
    executes is added to it (:func:`~scitex_clew._chain._notebook.notebook_code_files`):
    a notebook run's notebook is its ``script``, not an input row, yet a slice
    must carry it to re-execute the run. ``input_hashes(sid)`` gives the run's
    input rows (the driving notebook of a ``%run`` session is one).
    """
    from ._notebook import notebook_code_files, rerun_recipe

    out: dict[str, dict] = {}
    for sid in runs:
        run = db.get_run(sid)
        recipe = rerun_recipe(run)
        if recipe is None:
            continue
        out[sid] = recipe
        if files is not None:
            hashes = input_hashes(sid) if input_hashes else {}
            for path, digest in notebook_code_files(run, hashes).items():
                files.setdefault(path, digest)
    return out


def run_links(db, sid: str) -> list[dict]:
    """The symlink entries recorded for run ``sid`` (``metadata["links"]``)."""
    meta = _run_metadata(db, sid) or {}
    links = meta.get("links") or []
    return [e for e in links if isinstance(e, dict) and e.get("link")]


def collect_links(db, runs, kept_in, kept_out) -> dict[str, dict]:
    """``{link: entry}`` for every recorded link reaching a KEPT file.

    ``entry`` is the recorded one (see :mod:`scitex_clew._links`) with
    ``files`` narrowed to the kept files it reaches and ``runs`` listing the
    kept runs that went through it. Every hop of a chain is its own entry.
    """
    found: dict[str, dict] = {}
    for sid in runs:
        kept = set(kept_in.get(sid, ())) | set(kept_out.get(sid, ()))
        for entry in run_links(db, sid):
            files = [f for f in entry.get("files") or [] if f in kept]
            if not files:
                continue
            known = found.setdefault(entry["link"], {**entry, "files": [], "runs": []})
            known["files"] = sorted(set(known["files"]) | set(files))
            if sid not in known["runs"]:
                known["runs"].append(sid)
    return found


# EOF
