#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_viz/_mermaid_dag.py
"""DAG-building helpers for Mermaid diagram generation."""

from __future__ import annotations

from typing import Any, Literal

from .._chain import VerificationLevel, verify_run
from .._db import get_db
from .._groupers._base import FileEntry
from .._groupers._spec import resolve_spec
from ._json import format_path
from ._mermaid_nodes import (
    add_file_nodes,
    add_grouped_nodes,
    add_script_node,
    append_class_definitions,
)

PathMode = Literal["name", "relative", "absolute"]


def collect_runs_data(chain_ids: list, db) -> list:
    """Collect run data for all sessions in chain."""
    runs_data = []
    for sid in chain_ids:
        run = db.get_run(sid)
        verification = verify_run(sid)

        latest_verification = db.get_latest_verification(sid)
        if (
            latest_verification
            and latest_verification.get("level") == "rerun"
            and latest_verification.get("status") == "verified"
        ):
            verification.level = VerificationLevel.RERUN

        inputs = db.get_file_hashes(sid, role="input")
        outputs = db.get_file_hashes(sid, role="output")
        frozen_inputs = db.get_frozen_files(sid, role="input")
        frozen_outputs = db.get_frozen_files(sid, role="output")
        runs_data.append(
            {
                "session_id": sid,
                "run": run,
                "verification": verification,
                "inputs": inputs,
                "outputs": outputs,
                "frozen_inputs": frozen_inputs,
                "frozen_outputs": frozen_outputs,
            }
        )
    return runs_data


def generate_simple_dag(
    lines: list,
    runs_data: list,
    chain_ids: list,
    path_mode: PathMode = "name",
) -> None:
    """Generate simple script-only DAG."""
    for data in runs_data:
        sid = data["session_id"]
        run = data["run"]
        verification = data["verification"]
        node_id = sid.replace("-", "_").replace(".", "_")
        status_class = "verified" if verification.is_verified else "failed"
        script_name = format_path(
            run.get("script_path", "unknown") if run else "unknown", path_mode
        )
        lines.append(f'    {node_id}["{script_name}"]:::{status_class}')

    for i in range(len(chain_ids) - 1):
        curr = chain_ids[i].replace("-", "_").replace(".", "_")
        parent = chain_ids[i + 1].replace("-", "_").replace(".", "_")
        lines.append(f"    {parent} --> {curr}")


def _files_dict_to_entries(files: dict, role: str, session_id: str) -> list:
    return [
        FileEntry(path=p, hash=h, role=role, session_id=session_id)
        for p, h in files.items()
    ]


def generate_detailed_dag(
    lines: list,
    runs_data: list,
    show_hashes: bool = False,
    path_mode: PathMode = "name",
    grouper: Any | None = None,
) -> None:
    """Generate detailed DAG with input/output files and verification status.

    ``grouper`` accepts a callable, a dict spec, or ``None``. When non-None,
    per-session file lists are passed through the grouper to collapse
    related files into group nodes (each carrying a Merkle root).
    """
    from ._json import verify_file_hash

    node_ids: dict = {}
    failed_files: set = set()
    frozen_files: set = set()
    runs_data = list(reversed(runs_data))

    # Collect all frozen file paths across all sessions BEFORE hash checking
    # so we can skip hash verification for frozen files (their pre-computed
    # hashes are intentionally not re-verified on disk).
    for data in runs_data:
        frozen_files |= data.get("frozen_inputs", set())
        frozen_files |= data.get("frozen_outputs", set())

    for data in runs_data:
        inputs = data["inputs"]
        outputs = data["outputs"]
        for fpath, stored_hash in {**inputs, **outputs}.items():
            # Skip hash check for frozen files — they trust their recorded hash.
            if fpath in frozen_files:
                continue
            if not verify_file_hash(fpath, stored_hash):
                failed_files.add(fpath)

    for data in runs_data:
        inputs = data["inputs"]
        has_failed_input = any(fpath in failed_files for fpath in inputs.keys())
        if has_failed_input:
            for fpath in data["outputs"].keys():
                failed_files.add(fpath)

    group_fn = resolve_spec(grouper) if grouper is not None else None

    for i, data in enumerate(runs_data):
        sid = data["session_id"]
        run = data["run"]
        verification = data["verification"]
        inputs = data["inputs"]
        outputs = data["outputs"]

        has_failed_input = any(fpath in failed_files for fpath in inputs.keys())
        add_script_node(
            lines, i, sid, run, verification, path_mode, show_hashes, has_failed_input
        )
        is_rerun = verification.is_verified_from_scratch
        script_id = f"script_{i}"

        if group_fn is None:
            add_file_nodes(
                lines, script_id, inputs, node_ids, show_hashes, path_mode,
                "input", False, failed_files, None, frozen_files,
            )
            add_file_nodes(
                lines, script_id, outputs, node_ids, show_hashes, path_mode,
                "output", is_rerun, failed_files, None, frozen_files,
            )
        else:
            in_entries = _files_dict_to_entries(inputs, "input", sid)
            out_entries = _files_dict_to_entries(outputs, "output", sid)
            add_grouped_nodes(
                lines, script_id, group_fn(in_entries), node_ids, show_hashes,
                path_mode, "input", False, failed_files, None, frozen_files,
            )
            add_grouped_nodes(
                lines, script_id, group_fn(out_entries), node_ids, show_hashes,
                path_mode, "output", is_rerun, failed_files, None, frozen_files,
            )


def generate_multi_target_dag(
    target_files: list[str] | None = None,
    claims: bool = False,
    show_files: bool = True,
    show_hashes: bool = False,
    path_mode: PathMode = "name",
    grouper: Any | None = None,
) -> str:
    """Generate Mermaid diagram for a multi-target DAG."""
    lines = ["graph TD"]

    if claims:
        from .._claim import verify_claims_dag

        dag = verify_claims_dag()
    elif target_files:
        from .._dag import verify_dag

        dag = verify_dag(target_files)
    else:
        lines.append('    empty["No targets specified"]')
        return "\n".join(lines)

    if not dag.runs:
        lines.append('    empty["No runs found"]')
        return "\n".join(lines)

    db = get_db()
    verifications = {r.session_id: r for r in dag.runs}

    runs_data = []
    for sid in dag.topological_order:
        run = db.get_run(sid)
        verification = verifications.get(sid)
        if not verification:
            continue
        inputs = db.get_file_hashes(sid, role="input")
        outputs = db.get_file_hashes(sid, role="output")
        frozen_inputs = db.get_frozen_files(sid, role="input")
        frozen_outputs = db.get_frozen_files(sid, role="output")
        runs_data.append(
            {
                "session_id": sid,
                "run": run,
                "verification": verification,
                "inputs": inputs,
                "outputs": outputs,
                "frozen_inputs": frozen_inputs,
                "frozen_outputs": frozen_outputs,
            }
        )

    if show_files:
        generate_detailed_dag(lines, runs_data, show_hashes, path_mode, grouper=grouper)
    else:
        generate_simple_dag(
            lines,
            runs_data,
            [d["session_id"] for d in runs_data],
            path_mode,
        )

    append_class_definitions(lines)
    return "\n".join(lines)


# EOF
