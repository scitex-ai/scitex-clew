#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_viz/_mermaid_nodes.py
"""Node-building helpers for Mermaid DAG diagrams."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .._groupers._base import FileEntry, Group
from ._json import file_to_node_id, format_path, verify_file_hash

PathMode = Literal["name", "relative", "absolute"]


def get_file_icon(filename: str) -> str:
    """Get icon emoji for file type."""
    ext = Path(filename).suffix.lower()
    icons = {
        ".py": "🐍",
        ".csv": "📊",
        ".json": "📋",
        ".yaml": "⚙️",
        ".yml": "⚙️",
        ".png": "🖼️",
        ".jpg": "🖼️",
        ".jpeg": "🖼️",
        ".svg": "🖼️",
        ".pdf": "📄",
        ".html": "🌐",
        ".txt": "📝",
        ".md": "📝",
        ".npy": "🔢",
        ".npz": "🔢",
        ".pkl": "📦",
        ".pickle": "📦",
        ".h5": "💾",
        ".hdf5": "💾",
        ".mat": "🔬",
        ".sh": "🖥️",
    }
    return icons.get(ext, "📄")


def append_class_definitions(lines: list) -> None:
    """Append Mermaid class definitions for styling.

    Schema v1.3: color-only palette, zero status glyphs. The DAG view keeps
    full-7 fidelity (author tooling) — node fills match the full-7 ``palette``
    in claims.json:
      - verified  → green  #2da44e
      - suspect   → amber  #d29922
      - failed/mismatch → red #cf222e
      - exception → violet #8250df  (solid fill, no dashed)
      - frozen    → blue   #0072b2  (distinct trusted-hash hue; readers see
        it collapsed into the verified bucket, the DAG keeps it distinct)

    The colour bands let the DAG view distinguish locally-valid runs whose
    UPSTREAM chain is broken (amber ``suspect`` band) from runs whose own
    artifacts are wrong (red ``failed`` / ``file_bad`` band). See
    ``VerificationStatus.SUSPECT`` in ``_chain/_types.py`` for the underlying
    enum. Renderers that pass an empty ``suspect_files`` set degrade cleanly
    to the historical 2-colour output.
    """
    lines.append("")
    lines.append("    classDef script fill:#87CEEB,stroke:#4169E1,stroke-width:2px")
    lines.append("    classDef verified fill:#2da44e,stroke:#1a6b32")
    lines.append(
        "    classDef verified_scratch fill:#2da44e,stroke:#1a6b32,stroke-width:4px"
    )
    lines.append("    classDef failed fill:#cf222e,stroke:#8b1a1a")
    lines.append("    classDef suspect fill:#d29922,stroke:#8a5c00")
    lines.append("    classDef file fill:#FFF8DC,stroke:#DAA520")
    lines.append("    classDef file_ok fill:#2da44e,stroke:#1a6b32")
    lines.append("    classDef file_rerun fill:#2da44e,stroke:#1a6b32,stroke-width:4px")
    lines.append("    classDef file_bad fill:#cf222e,stroke:#8b1a1a")
    lines.append("    classDef file_suspect fill:#d29922,stroke:#8a5c00")
    lines.append(
        "    classDef file_frozen fill:#0072b2,stroke:#004a75"
    )
    lines.append(
        "    classDef exception fill:#8250df,stroke:#4a1c8a"
    )
    # Schema v1.4 (registered-source gate): burnt-amber for a node/claim whose
    # provenance chain reaches no registered source. Distinct from suspect amber
    # (#d29922) and clears the CUD delta-E floor against all 7 other states.
    lines.append("    classDef unsourced fill:#b26a00,stroke:#5c3600")
    lines.append("    classDef file_unsourced fill:#b26a00,stroke:#5c3600")


def add_script_node(
    lines: list,
    idx: int,
    sid: str,
    run: dict,
    verification,
    path_mode: PathMode,
    show_hashes: bool = False,
    has_failed_input: bool = False,
    has_suspect_input: bool = False,
) -> None:
    """Add a script node to the diagram.

    ``has_suspect_input`` is the orange-band signal: every local input
    file verifies, but the upstream chain producing one of those inputs
    failed. Caller flips this on for runs marked
    ``VerificationStatus.SUSPECT``; we then render the script in the
    ``suspect`` colour class so the DAG view does not lie that the run
    is green. Severity order is failed > suspect > verified.
    """
    node_id = f"script_{idx}"
    script_verified = verification.is_verified and not has_failed_input
    is_from_scratch = verification.is_verified_from_scratch and not has_failed_input

    # Determine whether this run was manually exception (not auto-tracked).
    is_exception = (run.get("provenance") == "exception") if run else False
    exception_reason = run.get("exception_reason") if run else None

    if has_failed_input:
        status_class = "failed"
    elif has_suspect_input:
        # Locally valid but upstream-broken — orange.
        status_class = "suspect"
    elif is_from_scratch:
        status_class = "verified_scratch"
    elif script_verified:
        # Apply dashed exception class only when the run is otherwise healthy
        # (no local/upstream failure). An exception node that fails keeps the
        # failure signal so the DAG view does not lie.
        status_class = "exception" if is_exception else "verified"
    else:
        status_class = "failed"

    script_path = run.get("script_path", "unknown") if run else "unknown"
    script_name = format_path(script_path, path_mode)
    icon = get_file_icon(script_path)
    short_id = sid.split("_")[-1][:4] if "_" in sid else sid[:8]
    badge = "✓✓" if is_from_scratch else ("✓" if script_verified else "✗")
    # Schema v1.3: exception label shows reason text only (no ⊘/EXCEPTION glyph).
    # The node COLOR (violet #8250df) conveys exception status.
    exception_label = ""
    if is_exception:
        reason_text = exception_reason or "no reason given"
        exception_label = f"<br/>[exception: {reason_text}]"
    script_hash = run.get("script_hash", "") if run else ""
    hash_display = f"<br/>{script_hash[:8]}..." if show_hashes and script_hash else ""
    lines.append(
        f'    {node_id}["{badge} {icon} {script_name}'
        f'<br/>(RUN: {short_id}){hash_display}{exception_label}"]:::{status_class}'
    )


def add_file_nodes(
    lines: list,
    script_id: str,
    files: dict,
    file_nodes: dict,
    show_hashes: bool,
    path_mode: PathMode,
    role: str,
    is_script_rerun_verified: bool = False,
    failed_files: set = None,
    suspect_files: set = None,
    frozen_files: set = None,
) -> None:
    """Add file nodes and connections to the diagram.

    ``suspect_files`` is the new orange-band signal (paired with the
    ``VerificationStatus.SUSPECT`` enum in ``_chain/_types.py``): a path
    in this set verifies locally (its own hash is fine), but the
    upstream session that produced it failed verification, so the chain
    is broken even though the artifact itself is. Callers that want the
    historical 2-colour output simply pass ``None`` (default) and the
    cascade falls back to file_ok / file_bad.

    ``frozen_files`` is the blue signal for files whose hash is trusted
    without re-reading (e.g. huge external datasets). A frozen file is
    NEVER silently shown as file_ok — it uses the ``file_frozen`` class
    (blue #0072b2, color-only) plus a plain-text label suffix.

    Severity preserved: failed > suspect > frozen > rerun > verified.
    """
    failed_files = failed_files or set()
    suspect_files = suspect_files or set()
    frozen_files = frozen_files or set()

    for fpath, stored_hash in files.items():
        display_name = format_path(fpath, path_mode)
        file_id = file_to_node_id(Path(fpath).name)
        icon = get_file_icon(fpath)

        if file_id not in file_nodes:
            # For frozen files, skip the disk hash check — they trust recorded hash.
            # A frozen file is shown as file_frozen (never file_bad from hash check).
            is_explicitly_failed = fpath in failed_files
            if fpath in frozen_files:
                # Frozen: only fail if explicitly in failed_files (e.g. truly missing).
                is_failed = is_explicitly_failed
            else:
                file_status = verify_file_hash(fpath, stored_hash)
                is_failed = is_explicitly_failed or not file_status
            is_suspect = (not is_failed) and (fpath in suspect_files)
            is_frozen = (not is_failed) and (not is_suspect) and (fpath in frozen_files)

            if is_failed:
                file_class = "file_bad"
                badge = "✗"
                frozen_label = ""
            elif is_suspect:
                file_class = "file_suspect"
                badge = "?"
                frozen_label = ""
            elif is_frozen:
                # Schema v1.3: color-only — no 🔒 icon. The trusted-hash state
                # is conveyed by the distinct frozen blue (#0072b2).
                file_class = "file_frozen"
                badge = "✓"
                frozen_label = "<br/>(frozen, not re-hashed)"
            elif role == "output" and is_script_rerun_verified:
                file_class = "file_rerun"
                badge = "✓✓"
                frozen_label = ""
            else:
                file_class = "file_ok"
                badge = "✓"
                frozen_label = ""

            hash_display = f"<br/>{stored_hash[:8]}..." if show_hashes else ""
            lines.append(
                f'    {file_id}[("{badge} {icon} {display_name}'
                f'{hash_display}{frozen_label}")]:::{file_class}'
            )
            file_nodes[file_id] = (fpath, stored_hash)

        if role == "input":
            lines.append(f"    {file_id} --> {script_id}")
        else:
            lines.append(f"    {script_id} --> {file_id}")


def add_grouped_nodes(
    lines: list,
    script_id: str,
    items: list,
    node_ids: dict,
    show_hashes: bool,
    path_mode: PathMode,
    role: str,
    is_script_rerun_verified: bool = False,
    failed_files: set = None,
    suspect_files: set = None,
    frozen_files: set = None,
) -> None:
    """Add file-or-group nodes and connections.

    ``items`` is a list mixing ``FileEntry`` and ``Group`` objects produced
    by a grouper. File entries render identically to ``add_file_nodes``;
    groups render as a single node labeled with member count and Merkle
    root, with aggregate verification status.

    ``suspect_files`` is propagated through to the single-file and group
    helpers so the SUSPECT (orange) band is honoured at every level of
    the DAG renderer. Default ``None`` → empty set → legacy 2-colour
    behaviour for callers that have not opted in yet.

    ``frozen_files`` is propagated so the frozen (blue #0072b2) band is
    honoured at every level. Default ``None`` → empty set → frozen
    behaviour only when explicitly passed.
    """
    failed_files = failed_files or set()
    suspect_files = suspect_files or set()
    frozen_files = frozen_files or set()

    for item in items:
        if isinstance(item, Group):
            _add_group_node(
                lines,
                script_id,
                item,
                node_ids,
                show_hashes,
                path_mode,
                role,
                is_script_rerun_verified,
                failed_files,
                suspect_files,
                frozen_files,
            )
        else:  # FileEntry
            _add_single_file_node(
                lines,
                script_id,
                item,
                node_ids,
                show_hashes,
                path_mode,
                role,
                is_script_rerun_verified,
                failed_files,
                suspect_files,
                frozen_files,
            )


def _add_single_file_node(
    lines,
    script_id,
    entry: FileEntry,
    node_ids,
    show_hashes,
    path_mode,
    role,
    is_rerun,
    failed_files,
    suspect_files=None,
    frozen_files=None,
):
    suspect_files = suspect_files or set()
    frozen_files = frozen_files or set()
    fpath = entry.path
    stored_hash = entry.hash
    display_name = format_path(fpath, path_mode)
    file_id = file_to_node_id(fpath)
    icon = get_file_icon(fpath)

    if file_id not in node_ids:
        is_explicitly_failed = fpath in failed_files
        if fpath in frozen_files:
            is_failed = is_explicitly_failed
        else:
            ok = verify_file_hash(fpath, stored_hash)
            is_failed = is_explicitly_failed or not ok
        is_suspect = (not is_failed) and (fpath in suspect_files)
        is_frozen = (not is_failed) and (not is_suspect) and (fpath in frozen_files)
        if is_failed:
            cls, badge, frozen_label = "file_bad", "✗", ""
        elif is_suspect:
            cls, badge, frozen_label = "file_suspect", "?", ""
        elif is_frozen:
            # Schema v1.3: color-only — frozen blue (#0072b2), no 🔒 icon.
            cls, badge, frozen_label = (
                "file_frozen",
                "✓",
                "<br/>(frozen, not re-hashed)",
            )
        elif role == "output" and is_rerun:
            cls, badge, frozen_label = "file_rerun", "✓✓", ""
        else:
            cls, badge, frozen_label = "file_ok", "✓", ""
        hash_display = f"<br/>{stored_hash[:8]}..." if show_hashes else ""
        lines.append(
            f'    {file_id}[("{badge} {icon} {display_name}'
            f'{hash_display}{frozen_label}")]:::{cls}'
        )
        node_ids[file_id] = ("file", fpath)

    if role == "input":
        lines.append(f"    {file_id} --> {script_id}")
    else:
        lines.append(f"    {script_id} --> {file_id}")


def _add_group_node(
    lines,
    script_id,
    group: Group,
    node_ids,
    show_hashes,
    path_mode,
    role,
    is_rerun,
    failed_files,
    suspect_files=None,
    frozen_files=None,
):
    suspect_files = suspect_files or set()
    frozen_files = frozen_files or set()
    group_id = f"group_{group.root_hash[:12]}"
    if group_id not in node_ids:
        any_failed = any(m.path in failed_files for m in group.members)
        if not any_failed:
            # Skip hash check for frozen members — they trust their recorded hash.
            any_failed = not all(
                (m.path in frozen_files) or verify_file_hash(m.path, m.hash)
                for m in group.members
            )
        any_suspect = (not any_failed) and any(
            m.path in suspect_files for m in group.members
        )
        any_frozen = (not any_failed) and (not any_suspect) and any(
            m.path in frozen_files for m in group.members
        )
        if any_failed:
            cls, badge = "file_bad", "⚠"
        elif any_suspect:
            # Group aggregates SUSPECT when no member is locally failed
            # but at least one member's upstream chain is broken.
            cls, badge = "file_suspect", "?"
        elif any_frozen:
            # Schema v1.3: color-only — frozen blue (#0072b2), no 🔒 icon.
            cls, badge = "file_frozen", "✓"
        elif role == "output" and is_rerun:
            cls, badge = "file_rerun", "✓✓"
        else:
            cls, badge = "file_ok", "✓"
        icon = "🗂️"
        hash_display = f"<br/>root={group.root_hash[:8]}..." if show_hashes else ""
        lines.append(
            f'    {group_id}[/"{badge} {icon} {group.label}{hash_display}"\\]:::{cls}'
        )
        node_ids[group_id] = ("group", group.root_hash)

    if role == "input":
        lines.append(f"    {group_id} --> {script_id}")
    else:
        lines.append(f"    {script_id} --> {group_id}")


# EOF
