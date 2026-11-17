#!/usr/bin/env python3
"""Jupyter notebooks as the code of a run: identity, slice recipe, re-execution.

A session started inside a Jupyter kernel records (scitex-session >= 0.4.0)
``metadata["entry"] = {"kind": "notebook", "path": <.ipynb>, "invocation":
"cell" | "run" | "file", "code_sha256": ..., ...}``. For a ``@session`` called
in a cell the notebook is also the run's ``script_path``; for ``%run
script.py`` the script is, and the notebook is the code that ran it.

Identity
    A notebook's identity is its CODE: :func:`notebook_code_digest` hashes the
    code cells' sources only (scheme ``ipynb-code-v1``, byte-identical to
    scitex-session's ``code_sha256``), so executing the notebook again or
    saving it with new outputs / execution counts / metadata does not change
    it, while editing any code cell does. Clew stores it as
    :data:`NOTEBOOK_CODE_PREFIX` + digest; the prefix tells every verifier to
    re-hash the file the same way (:func:`scitex_clew._hash.hash_like`), and
    an ``.ipynb`` recorded as plain DATA keeps its byte hash.

Record
    :func:`record_notebook_input` makes the notebook an ``input`` row of the
    run (the edge slice, chain, verify and rerun staging already follow, as
    for an imported project module), so ``clew slice`` lists it and ``clew
    verify`` flags an edited notebook. A ``%run`` script stays a code input
    of its own: the run's ``script_path``, and an input row (byte hash).

Re-execution
    :func:`rerun_recipe` is the explicit recipe a slice carries per run:
    execute the notebook headless, top to bottom, from the recorded working
    directory — never a replay of the kernel's argv. A cell-by-cell
    interactive history (out of order, deleted cells) is NOT what the recipe
    reproduces; the session records whether the history matched the file
    (``entry["executed_in_order"]``). :func:`execute_notebook` runs it with
    ``nbclient`` (an optional dependency, imported only here; a clear error
    names what to install), with ``$SCITEX_NOTEBOOK_PATH`` naming the
    notebook so the kernel's session and scitex-io resolve it.

clew itself stays stdlib-only at import: nothing here imports nbclient until a
notebook is executed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

#: Prefix of a stored notebook CODE hash (vs a byte hash of the file).
NOTEBOOK_CODE_PREFIX = "ipynb-code-v1:"

#: Environment variable naming the notebook for the kernel (scitex-io and
#: scitex-session read it).
NOTEBOOK_PATH_ENV = "SCITEX_NOTEBOOK_PATH"

#: Exit status of ``python -m scitex_clew execute-notebook`` when the optional
#: executor is not installed.
EXIT_NO_EXECUTOR = 3


def _normalise(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


def notebook_code_cells(path: str | Path) -> list[str]:
    """Sources of the notebook's code cells, in order (nbformat 4, or 3)."""
    with open(path, encoding="utf-8") as fh:
        nb = json.load(fh)
    cells = nb.get("cells")
    if cells is None:  # nbformat 3
        cells = [c for ws in nb.get("worksheets") or [] for c in ws.get("cells") or []]
    out = []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", cell.get("input", ""))
        if isinstance(src, list):
            src = "".join(src)
        out.append(_normalise(str(src)))
    return out


def notebook_code_digest(path: str | Path) -> str:
    """SHA-256 of the notebook's code cells (scheme ``ipynb-code-v1``).

    The digest of the UTF-8 JSON array of the code-cell sources, newlines
    normalised to ``\\n``, compact separators, non-ASCII kept.
    """
    payload = json.dumps(
        notebook_code_cells(path), ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_notebook_code(path: str | Path) -> str:
    """Stored form of a notebook's code identity: prefix + digest."""
    return NOTEBOOK_CODE_PREFIX + notebook_code_digest(path)


def is_notebook_code_hash(value: str | None) -> bool:
    return bool(value) and str(value).startswith(NOTEBOOK_CODE_PREFIX)


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------


def run_metadata(run_info: dict | None) -> dict:
    raw = (run_info or {}).get("metadata")
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return dict(raw)


def notebook_of(metadata: dict | None) -> dict | None:
    """The run's notebook entry (``kind == notebook`` with a path), else None."""
    entry = (metadata or {}).get("entry") or {}
    if entry.get("kind") != "notebook" or not entry.get("path"):
        return None
    return entry


def record_notebook_input(tracker, metadata: dict | None) -> list[str]:
    """Record the code a notebook run executed as INPUT rows (see module doc).

    The notebook itself (identity = code cells), and — for a ``%run
    script.py`` session, whose ``script_path`` is the script — the script
    too (byte hash): from the notebook's point of view it is code the
    notebook ran, and a slice must carry both to re-execute the notebook.
    Returns the recorded paths ([] for a run without a resolved notebook).
    """
    entry = notebook_of(metadata)
    if entry is None:
        return []
    from .._hash import hash_file

    found: dict[str, str] = {}
    path = os.path.realpath(str(entry["path"]))
    if os.path.isfile(path):
        found[path] = hash_notebook_code(path)
    script = getattr(tracker, "script_path", None)
    if entry.get("invocation") == "run" and script and os.path.isfile(script):
        real = os.path.realpath(str(script))
        if real != path:
            found[real] = hash_file(real)
    if found:
        tracker.record_hashed_inputs(found)
    return sorted(found)


# ---------------------------------------------------------------------------
# Re-execution recipe
# ---------------------------------------------------------------------------


def rerun_recipe(run_info: dict | None) -> dict | None:
    """How to re-execute a notebook run, or None for a non-notebook run.

    ``{"kind": "notebook", "path", "cwd", "python", "argv", "command", "env",
    "invocation", "script", "caveat"}``: ``argv`` is relative to ``python``
    (``python *argv``), ``command`` the full command line, ``env`` what to add
    to the environment. Run it from ``cwd``.
    """
    meta = run_metadata(run_info)
    entry = notebook_of(meta)
    if entry is None:
        return None
    path = str(entry["path"])
    cwd = meta.get("cwd") or str(Path(path).parent)
    python = (meta.get("python") or {}).get("executable") or "python"
    argv = ["-m", "scitex_clew", "execute-notebook", path, "--cwd", cwd]
    recipe = {
        "kind": "notebook",
        "path": path,
        "cwd": cwd,
        "python": python,
        "argv": argv,
        "command": [python, *argv],
        "env": {NOTEBOOK_PATH_ENV: path},
        "invocation": entry.get("invocation"),
        "script": (run_info or {}).get("script_path") or None,
        "caveat": (
            "re-executes the notebook headless, top to bottom; the original "
            "kernel's out-of-order or since-deleted cells are not replayed"
            + (
                ""
                if entry.get("executed_in_order", True)
                else " — and this run's history did NOT match the file in order"
            )
        ),
    }
    return recipe


def execute_notebook(
    path: str | Path,
    cwd: str | Path | None = None,
    *,
    timeout: int | None = None,
    kernel_name: str | None = None,
) -> None:
    """Execute ``path`` headless in a fresh kernel whose cwd is ``cwd``.

    The notebook file is not modified. ``$SCITEX_NOTEBOOK_PATH`` is set to it
    for the kernel. Raises ``ModuleNotFoundError`` with an install hint when
    ``nbclient`` / ``nbformat`` / ``ipykernel`` are missing, and
    ``nbclient``'s ``CellExecutionError`` when a cell fails.
    """
    try:
        import nbclient
        import nbformat
    except ImportError as exc:
        raise ModuleNotFoundError(
            f"clew: re-executing a notebook needs nbclient + nbformat + ipykernel "
            f"({exc}); install them into {sys.executable}: "
            "pip install nbclient nbformat ipykernel"
        ) from exc
    path = os.path.realpath(str(path))
    cwd = os.path.realpath(str(cwd)) if cwd else os.path.dirname(path)
    nb = nbformat.read(path, as_version=4)
    os.environ[NOTEBOOK_PATH_ENV] = path  # inherited by the kernel
    # The native kernel runs THIS interpreter — the run's recorded python
    # when invoked through the recipe — whatever kernelspec the file names.
    name = kernel_name or "python3"
    client = nbclient.NotebookClient(
        nb, timeout=timeout, kernel_name=name, resources={"metadata": {"path": cwd}}
    )
    client.execute()


# EOF
