#!/usr/bin/env python3
# Timestamp: "2026-06-30 (ywatanabe)"
# File: src/scitex_clew/_viz/_image_dag.py
"""DAG data builder for the matplotlib image renderer.

Reuses the same DB API and hash-verification logic as the mermaid renderer
(``_mermaid_dag.py``) without duplicating the DAG-construction code.

Public API
----------
build_dag_graph(targets, claims, max_depth, show_files, grouper)
    Returns (nodes, edges) ready for the layout and rendering steps.
"""

from __future__ import annotations

from typing import Any


def _add_file_node(
    nodes: list[dict],
    file_node_id: str,
    fpath: str,
    stored_hash: str,
    role: str,
    failed_files: set[str],
    frozen_files: set[str],
    is_rerun: bool,
) -> None:
    """Append one file-node dict to *nodes*."""
    from pathlib import Path as _Path
    from ._json import verify_file_hash

    display_name = _Path(fpath).name
    is_explicitly_failed = fpath in failed_files
    if fpath in frozen_files:
        is_failed = is_explicitly_failed
    else:
        is_failed = is_explicitly_failed or not verify_file_hash(fpath, stored_hash)

    is_frozen = (not is_failed) and (fpath in frozen_files)

    if is_failed:
        status = "file_bad"
        label = f"✗ {display_name}"  # ✗
    elif is_frozen:
        # Schema v1.3: color-only — no 🔒 glyph; blue conveys frozen state.
        status = "file_frozen"
        label = f"{display_name}\nFROZEN"
    elif role == "output" and is_rerun:
        status = "file_rerun"
        label = f"✓✓ {display_name}"  # ✓✓
    else:
        status = "file_ok"
        label = f"✓ {display_name}"  # ✓

    nodes.append({
        "id": file_node_id,
        "label": label,
        "status": status,
        "node_type": "file",
        "is_exception": False,
        "exception_reason": None,
        "is_frozen": is_frozen,
    })


def _collect_runs_from_dag(dag, db) -> list[dict]:
    """Build runs_data list from a DAGVerification object + db."""
    verifications = {r.session_id: r for r in dag.runs}
    runs_data: list[dict] = []
    for sid in dag.topological_order:
        run = db.get_run(sid)
        verification = verifications.get(sid)
        if not verification:
            continue
        runs_data.append({
            "session_id": sid,
            "run": run,
            "verification": verification,
            "inputs": db.get_file_hashes(sid, role="input"),
            "outputs": db.get_file_hashes(sid, role="output"),
            "frozen_inputs": db.get_frozen_files(sid, role="input"),
            "frozen_outputs": db.get_frozen_files(sid, role="output"),
        })
    return runs_data


def build_dag_graph(
    targets: list[str] | None = None,
    claims: bool = False,
    max_depth: int = 10,
    show_files: bool = True,
    grouper: Any | None = None,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Build (nodes, edges) for the provenance DAG.

    Node dicts have keys: id, label, status, node_type, is_exception,
    exception_reason, is_frozen.  Edge tuples are (source_id, target_id)
    where the arrow flows source -> target.

    Reuses the DB API calls identical to ``generate_multi_target_dag`` in
    ``_mermaid_dag.py`` — no duplicated DAG-building logic.
    """
    from pathlib import Path as _Path
    from .._chain import verify_run
    from .._db import get_db
    from ._json import file_to_node_id, verify_file_hash

    db = get_db()
    nodes: list[dict] = []
    edges: list[tuple[str, str]] = []
    node_ids: set[str] = set()

    # ---- Collect raw runs_data ------------------------------------------------
    if claims:
        from .._claim import verify_claims_dag
        dag = verify_claims_dag()
        runs_data = _collect_runs_from_dag(dag, db)
    elif targets:
        from .._chain import verify_dag
        dag = verify_dag(targets)
        runs_data = _collect_runs_from_dag(dag, db)
    else:
        all_runs = db.list_runs(limit=500)
        runs_data = []
        for row in all_runs:
            sid = row["session_id"]
            run = db.get_run(sid)
            verification = verify_run(sid)
            runs_data.append({
                "session_id": sid,
                "run": run,
                "verification": verification,
                "inputs": db.get_file_hashes(sid, role="input"),
                "outputs": db.get_file_hashes(sid, role="output"),
                "frozen_inputs": db.get_frozen_files(sid, role="input"),
                "frozen_outputs": db.get_frozen_files(sid, role="output"),
            })

    if not runs_data:
        return [], []

    # ---- Determine failed/frozen file sets ------------------------------------
    frozen_files: set[str] = set()
    for data in runs_data:
        frozen_files |= data.get("frozen_inputs", set())
        frozen_files |= data.get("frozen_outputs", set())

    failed_files: set[str] = set()
    for data in runs_data:
        for fpath, stored_hash in {**data["inputs"], **data["outputs"]}.items():
            if fpath in frozen_files:
                continue
            if not verify_file_hash(fpath, stored_hash):
                failed_files.add(fpath)

    # Cascade failures: if a session has failed inputs, its outputs also fail.
    for data in runs_data:
        if any(fp in failed_files for fp in data["inputs"]):
            failed_files.update(data["outputs"].keys())

    # ---- Build nodes and edges -----------------------------------------------
    for i, data in enumerate(reversed(runs_data)):
        sid = data["session_id"]
        run = data["run"]
        verification = data["verification"]
        inputs = data["inputs"]
        outputs = data["outputs"]

        is_exception = (run.get("provenance") == "exception") if run else False
        exception_reason = run.get("exception_reason") if run else None
        has_failed_input = any(fp in failed_files for fp in inputs)

        script_verified = verification.is_verified and not has_failed_input
        is_from_scratch = (
            getattr(verification, "is_verified_from_scratch", False)
            and not has_failed_input
        )

        if has_failed_input:
            status = "failed"
        elif is_from_scratch:
            status = "verified_scratch"
        elif script_verified:
            status = "exception" if is_exception else "verified"
        else:
            status = "failed"

        script_path = (run.get("script_path") or "unknown") if run else "unknown"
        script_name = _Path(script_path).name if script_path != "unknown" else "unknown"
        badge = "✓✓" if is_from_scratch else ("✓" if script_verified else "✗")
        label = f"{badge} {script_name}"
        if is_exception:
            # Schema v1.3: color-only — no ⊘ glyph; violet conveys exception.
            reason_text = exception_reason or "no reason given"
            label += f"\nEXCEPTION\n[{reason_text}]"

        script_node_id = f"script_{i}"
        nodes.append({
            "id": script_node_id,
            "label": label,
            "status": status,
            "node_type": "script",
            "is_exception": is_exception,
            "exception_reason": exception_reason,
            "is_frozen": False,
        })
        node_ids.add(script_node_id)

        if show_files:
            for fpath, stored_hash in inputs.items():
                fid = file_to_node_id(fpath)
                if fid not in node_ids:
                    _add_file_node(
                        nodes, fid, fpath, stored_hash, "input",
                        failed_files, frozen_files, False,
                    )
                    node_ids.add(fid)
                edges.append((fid, script_node_id))

            for fpath, stored_hash in outputs.items():
                fid = file_to_node_id(fpath)
                if fid not in node_ids:
                    _add_file_node(
                        nodes, fid, fpath, stored_hash, "output",
                        failed_files, frozen_files, is_from_scratch,
                    )
                    node_ids.add(fid)
                edges.append((script_node_id, fid))

    return nodes, edges


# EOF
