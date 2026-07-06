#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_viz/_mermaid.py
"""Mermaid diagram generation for verification DAG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .._chain import verify_chain
from .._db import get_db
from ._json import generate_dag_json
from ._mermaid_dag import (
    collect_runs_data,
    generate_detailed_dag,
    generate_multi_target_dag,
    generate_simple_dag,
)
from ._mermaid_nodes import append_class_definitions
from ._templates import get_html_template

PathMode = Literal["name", "relative", "absolute"]


def generate_mermaid_dag(
    session_id: str | None = None,
    target_file: str | None = None,
    target_files: list[str] | None = None,
    claims: bool = False,
    max_depth: int = 10,
    show_files: bool = True,
    show_hashes: bool = False,
    path_mode: PathMode = "name",
    grouper=None,
) -> str:
    """
    Generate Mermaid diagram for verification DAG.

    Parameters
    ----------
    session_id : str, optional
        Start from this session
    target_file : str, optional
        Start from session that produced this file
    target_files : list of str, optional
        Start from sessions that produced these files (multi-target DAG)
    claims : bool, optional
        Use registered claims to build DAG (default: False)
    max_depth : int, optional
        Maximum chain depth
    show_files : bool, optional
        Whether to show input/output files as nodes (default: True)
    show_hashes : bool, optional
        Whether to show truncated file hashes (default: False)
    path_mode : str, optional
        How to display file paths: "name", "relative", or "absolute"

    Returns
    -------
    str
        Mermaid diagram code
    """
    if grouper is None:
        from .._groupers._config import load_project_config

        grouper = load_project_config().get("grouper")

    # Multi-target DAG mode
    if target_files or claims:
        return generate_multi_target_dag(
            target_files=target_files,
            claims=claims,
            show_files=show_files,
            show_hashes=show_hashes,
            path_mode=path_mode,
            grouper=grouper,
        )

    db = get_db()
    lines = ["graph TD"]

    if target_file:
        chain = verify_chain(target_file)
        chain_ids = [run.session_id for run in chain.runs]
    elif session_id:
        chain_ids = db.get_chain(session_id)
    else:
        all_runs = db.list_runs(limit=500)
        chain_ids = [r["session_id"] for r in all_runs]

    if not chain_ids:
        lines.append('    empty["No runs found"]')
        return "\n".join(lines)

    runs_data = collect_runs_data(chain_ids, db)

    if show_files:
        generate_detailed_dag(lines, runs_data, show_hashes, path_mode, grouper=grouper)
    else:
        generate_simple_dag(lines, runs_data, chain_ids, path_mode)

    append_class_definitions(lines)
    return "\n".join(lines)


def generate_html_dag(
    session_id: str | None = None,
    target_file: str | None = None,
    target_files: list[str] | None = None,
    claims: bool = False,
    title: str = "Verification DAG",
    show_hashes: bool = False,
    path_mode: PathMode = "name",
    grouper=None,
) -> str:
    """Generate interactive HTML visualization for verification DAG."""
    mermaid_code = generate_mermaid_dag(
        session_id=session_id,
        target_file=target_file,
        target_files=target_files,
        claims=claims,
        show_hashes=show_hashes,
        path_mode=path_mode,
        grouper=grouper,
    )
    return get_html_template(title, mermaid_code)


# Sentinel node lines emitted by the generators when the requested view
# resolves to zero runs. render_dag refuses to write these (fail loud).
_EMPTY_VIEW_MARKERS = (
    'empty["No runs found"]',
    'empty["No targets specified"]',
)


def _resolve_store_or_raise(db_path: str | Path | None):
    """Resolve the store per the three-tier precedence, failing loud.

    Returns a context manager that activates the resolved store for the
    duration of the render. When no explicit ``db_path`` is given and a
    global instance is already configured (``get_db()``/``set_db()``),
    that instance is kept untouched.

    Raises
    ------
    FileNotFoundError
        If the resolved store file does not exist.
    """
    from contextlib import nullcontext

    from .._db import get_active_db_path, resolve_db_path, use_db

    if db_path is None and get_active_db_path() is not None:
        return nullcontext()

    resolved, tier = resolve_db_path(db_path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"scitex-clew store not found: {resolved} (resolved via {tier}). "
            "Store resolution precedence: (1) explicit db_path argument, "
            "(2) SCITEX_CLEW_DB_PATH environment variable, (3) "
            "<project_root>/.scitex/clew/runtime/clew.db via project-root "
            "walk from the current working directory. Pass db_path=... to "
            "render a store that lives outside the current tree."
        )
    return use_db(resolved)


def _raise_empty_view(output_path: Path) -> None:
    """Fail loud instead of silently writing an empty diagram."""
    from .._db import get_db

    raise ValueError(
        f"scitex-clew store was found at {get_db().db_path} but the "
        f"requested DAG view is empty — refusing to write {output_path}. "
        "Check the filters (claims / session_id / target_file / "
        "target_files) or confirm the store actually contains runs."
    )


def render_dag(
    output_path: str | Path,
    session_id: str | None = None,
    target_file: str | None = None,
    target_files: list[str] | None = None,
    claims: bool = False,
    title: str = "Verification DAG",
    show_hashes: bool = False,
    path_mode: PathMode = "name",
    grouper=None,
    db_path: str | Path | None = None,
) -> Path:
    """
    Render verification DAG to file (HTML, PNG, SVG, JSON, or MMD).

    Parameters
    ----------
    output_path : str or Path
        Output file path. Extension determines format.
    session_id : str, optional
        Start from this session
    target_file : str, optional
        Start from session that produced this file
    target_files : list of str, optional
        Start from sessions that produced these files (multi-target DAG)
    claims : bool, optional
        Use registered claims to build DAG (default: False)
    title : str, optional
        Title for the visualization
    show_hashes : bool, optional
        Whether to show file hashes
    path_mode : str, optional
        Path display mode
    db_path : str or Path, optional
        Explicit path to the clew store (clew.db). Resolution precedence:
        (1) this argument, (2) the SCITEX_CLEW_DB_PATH environment variable,
        (3) project-root walk from the current working directory. Pass this
        to render a store that lives outside the current tree (e.g. a
        capsule's ``.scitex/clew/runtime/clew.db``) without chdir. Same
        semantics as ``VerificationDB(db_path=...)`` / ``set_db(db_path)``,
        but scoped to this call only.

    Returns
    -------
    Path
        Path to the generated file

    Raises
    ------
    FileNotFoundError
        If the resolved store file does not exist (names the path tried
        and the resolution tier).
    ValueError
        If the output extension is unsupported, or if the store exists but
        the requested view is empty (e.g. ``claims=True`` with zero claims,
        or filters matching nothing) — render_dag never returns without
        writing the requested file.
    """
    output_path = Path(output_path)
    ext = output_path.suffix.lower()

    if ext in (".sqlite", ".db"):
        # A caller passed the clew STORE path as the render target. clew
        # reads the DAG from the store INTERNALLY (via session_id/claims)
        # and infers the output format from THIS path's suffix — the
        # store is never a render target. Pass a dag.<ext> output path
        # instead (and db_path=... to pick the store explicitly).
        raise ValueError(
            f"'{ext}' is the clew store, not a render target — render_dag "
            "reads the DAG from the store internally. Pass an OUTPUT path "
            "ending in .png, .svg, .html, .json, or .mmd "
            "(e.g. render_dag('dag.png', claims=True)); use the db_path "
            "keyword to target a specific store."
        )
    if ext not in (".html", ".mmd", ".json", ".png", ".svg"):
        raise ValueError(
            f"Unsupported format: {ext}. Use .html, .png, .svg, .json, or .mmd"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _resolve_store_or_raise(db_path):
        if ext == ".html":
            content = generate_html_dag(
                session_id=session_id,
                target_file=target_file,
                target_files=target_files,
                claims=claims,
                title=title,
                show_hashes=show_hashes,
                path_mode=path_mode,
                grouper=grouper,
            )
            if any(marker in content for marker in _EMPTY_VIEW_MARKERS):
                _raise_empty_view(output_path)
            output_path.write_text(content)

        elif ext == ".mmd":
            content = generate_mermaid_dag(
                session_id=session_id,
                target_file=target_file,
                target_files=target_files,
                claims=claims,
                show_hashes=show_hashes,
                path_mode=path_mode,
                grouper=grouper,
            )
            if any(marker in content for marker in _EMPTY_VIEW_MARKERS):
                _raise_empty_view(output_path)
            output_path.write_text(content)

        elif ext == ".json":
            graph_json = generate_dag_json(
                session_id=session_id,
                target_file=target_file,
                target_files=target_files,
                claims=claims,
                path_mode=path_mode,
            )
            if not graph_json.get("nodes"):
                _raise_empty_view(output_path)
            output_path.write_text(json.dumps(graph_json, indent=2))

        elif ext in [".png", ".svg"]:
            mermaid = generate_mermaid_dag(
                session_id=session_id,
                target_file=target_file,
                target_files=target_files,
                claims=claims,
                show_hashes=show_hashes,
                path_mode=path_mode,
                grouper=grouper,
            )
            if any(marker in mermaid for marker in _EMPTY_VIEW_MARKERS):
                _raise_empty_view(output_path)
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".mmd", delete=False
            ) as f:
                f.write(mermaid)
                mmd_path = f.name

            try:
                subprocess.run(
                    ["mmdc", "-i", mmd_path, "-o", str(output_path)],
                    check=True,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                fallback_path = output_path.with_suffix(".mmd")
                fallback_path.write_text(mermaid)
                return fallback_path
            finally:
                Path(mmd_path).unlink(missing_ok=True)

    return output_path


# EOF
