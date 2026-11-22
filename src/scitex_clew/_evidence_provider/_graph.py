#!/usr/bin/env python3
"""A claim's level-1 provenance slice as a contract evidence graph.

Node kinds (contract ``scitex-live-paper.evidence-report`` 1.x):

* each kept run -> ``process`` (label: the run's session id; an optional
  ``script`` identifies the recorded in-project script and its hash);
* each kept file -> ``output`` when some kept run wrote it, else ``input``
  (label: the path relative to the project root, ``hash``: its recorded
  SHA-256; ``external: true`` for an input read from outside the project);
* the claim itself -> ``claim``.

Edges: input file -> run (``input``), run -> output file (``output``) and
each slice target (the claim's source file) -> claim (``supports``).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["relative_to_root", "slice_to_graph"]


def relative_to_root(path: str | None, root: Path) -> str | None:
    """``path`` relative to ``root`` when inside it, else unchanged."""
    if not path:
        return path
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def slice_to_graph(sl, claim_id: str, root: Path, *, run_lookup=None) -> dict:
    """Convert a :class:`~scitex_clew._chain._slice.ProvenanceSlice`."""
    nodes: list[dict] = []
    edges: list[dict] = []
    file_ids: dict[str, str] = {}
    written = {p for sid in sl.runs for p in sl.run_outputs.get(sid, [])}

    def file_node(path: str) -> str:
        if path not in file_ids:
            file_ids[path] = f"f{len(file_ids) + 1}"
            node = {
                "id": file_ids[path],
                "kind": "output" if path in written else "input",
                "label": relative_to_root(path, root),
                "hash": sl.file_hashes.get(path),
            }
            if path in sl.external:
                node["external"] = True
            nodes.append(node)
        return file_ids[path]

    for index, sid in enumerate(sl.runs, start=1):
        pid = f"p{index}"
        process = {"id": pid, "kind": "process", "label": str(sid)}
        run = (run_lookup(sid) or {}) if run_lookup is not None else {}
        script_path, script_hash = run.get("script_path"), run.get("script_hash")
        if script_path and script_hash:
            path = Path(script_path)
            # Paths are identified by the recorded absolute path. Resolving
            # today could swap an original script identity for a new symlink.
            if path.is_absolute() and path.is_relative_to(root) and ".." not in path.parts:
                process["script"] = {
                    "file": path.relative_to(root).as_posix(),
                    "hash": script_hash,
                }
        nodes.append(process)
        for path in sl.run_inputs.get(sid, []):
            edges.append({"source": file_node(path), "target": pid, "kind": "input"})
        for path in sl.run_outputs.get(sid, []):
            edges.append({"source": pid, "target": file_node(path), "kind": "output"})

    nodes.append({"id": "c", "kind": "claim", "label": claim_id})
    for target in sl.targets:
        edges.append({"source": file_node(target), "target": "c", "kind": "supports"})

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": f"level-{sl.level} slice: {len(sl.runs)} run(s), "
        f"{len(file_ids)} file(s)",
    }


# EOF
