#!/usr/bin/env python3
"""Per-run METADATA records a slice carries: software environment + symlinks.

Split out of :mod:`._slice` (512-line limit). Both come from the kept runs'
recorded metadata rather than from ``file_hashes`` rows:

* ``packages`` / ``unresolved_imports`` (scitex-session >= 0.3.6) — what a
  re-run must install;
* ``links`` (#192, :mod:`scitex_clew._links`) — the in-project symlinks the run
  went through to reach its files. A slice keeps a link when it reaches a
  kept file; materializing the slice must recreate it, or a re-run that opens
  the link path finds nothing.
"""

from __future__ import annotations

import json

__all__ = ["collect_links", "run_environment", "run_links", "run_metadata_of"]


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
    """``{"packages", "unresolved_imports"}`` recorded for run ``sid``."""
    meta = _run_metadata(db, sid)
    if meta is None or "packages" not in meta:
        return None
    packages = meta.get("packages")
    return {
        "packages": dict(packages) if isinstance(packages, dict) else None,
        "unresolved_imports": dict(meta.get("unresolved_imports") or {}),
    }


def collect_recipes(db, runs) -> dict[str, dict]:
    """``{sid: recipe}`` for every kept run that a notebook ran.

    A notebook run is re-executed by running the notebook (headless, top to
    bottom; :func:`scitex_clew._chain._notebook.rerun_recipe`), never by replaying
    the kernel's argv. Runs without a recipe replay their recorded argv.
    """
    from ._notebook import rerun_recipe

    out: dict[str, dict] = {}
    for sid in runs:
        recipe = rerun_recipe(db.get_run(sid))
        if recipe is not None:
            out[sid] = recipe
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
