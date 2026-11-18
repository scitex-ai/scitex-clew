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
    Each file has ONE role, as for a ``.py`` entry script. A notebook that is
    the run's ``script_path`` (in-cell ``@session``) is its ``script``:
    ``script_hash`` is its code identity, so ``clew verify`` flags an edited
    code cell through the script check. For a ``%run script.py`` session the
    script is the run's ``script`` and :func:`record_notebook_input` records
    the driving notebook as an ``input`` row (code the run did not start
    from, like an imported module). :func:`notebook_code_files` gives the
    code a run's recipe executes, which ``clew slice`` lists among its files.

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
import shutil
import sys
import tempfile
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
    """Record a notebook that ran the session, but is NOT its script, as input.

    One file, one role — as for a ``.py`` entry script. When the notebook IS
    the run's ``script_path`` (``@session`` called in a cell) it is the run's
    ``script`` (``script_hash`` = its code identity) and nothing is recorded
    here: an extra ``input`` row would file the run's own code as data it
    read. For a ``%run script.py`` session the script is the run's
    ``script``; the driving notebook is code the run did not start from, so
    it is an ``input`` row (identity = code cells), like an imported module.
    Returns the recorded paths ([] when there is nothing to record).
    """
    entry = notebook_of(metadata)
    if entry is None:
        return []
    path = os.path.realpath(str(entry["path"]))
    script = getattr(tracker, "script_path", None)
    if not os.path.isfile(path) or (script and os.path.realpath(str(script)) == path):
        return []
    tracker.record_hashed_inputs({path: hash_notebook_code(path)})
    return [path]


def notebook_code_files(run_info: dict | None, input_hashes: dict) -> dict:
    """``{path: stored hash}`` of the code a notebook run's recipe executes.

    The notebook and, for a ``%run`` session, the script it ran — each with
    the hash recorded for it in its one role (``script_hash`` for the run's
    script, the input row otherwise; None if neither). A slice carries these
    so it can re-execute the run. ``{}`` for a non-notebook run.
    """
    entry = notebook_of(run_metadata(run_info))
    if entry is None:
        return {}
    run_info = run_info or {}
    script = run_info.get("script_path") or None
    real_script = os.path.realpath(script) if script else None
    out: dict = {}
    for path in (str(entry["path"]), script):
        if not path:
            continue
        if real_script and os.path.realpath(path) == real_script:
            out[path] = run_info.get("script_hash")
        else:
            out[path] = input_hashes.get(path, input_hashes.get(os.path.realpath(path)))
    return out


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
    channels = kernel_channel_dir()
    try:
        client = nbclient.NotebookClient(
            nb,
            km=_private_kernel_manager(name, channels),
            timeout=timeout,
            kernel_name=name,
            resources={"metadata": {"path": cwd}},
        )
        client.execute()
    finally:
        shutil.rmtree(channels, ignore_errors=True)


#: Longest Unix-domain socket path (``sizeof(sockaddr_un.sun_path) - 1`` on
#: Linux; macOS allows 103, so the margin below covers both).
_SOCKET_PATH_MAX = 103
#: ``/clew-kernel-XXXXXXXX/kernel-NN`` appended to the base directory.
_CHANNEL_SUFFIX_LEN = 32


def kernel_channel_dir() -> str:
    """A fresh private directory for one kernel's ``ipc`` sockets (caller removes).

    Under the temp dir when the socket paths fit the OS limit there
    (``sun_path``: 107 bytes on Linux, 103 on macOS); a deep ``$TMPDIR`` (a CI
    runner's work tree, a macOS per-user folder) does not, so ``/tmp`` is
    used then. Raises ``OSError`` naming the limit when neither fits.
    """
    for base in (tempfile.gettempdir(), "/tmp"):
        if len(base) + _CHANNEL_SUFFIX_LEN <= _SOCKET_PATH_MAX and os.path.isdir(base):
            return tempfile.mkdtemp(prefix="clew-kernel-", dir=base)
    raise OSError(
        f"clew: no directory short enough for kernel sockets "
        f"(<= {_SOCKET_PATH_MAX - _CHANNEL_SUFFIX_LEN} chars): "
        f"{tempfile.gettempdir()!r} and /tmp"
    )


def _private_kernel_manager(kernel_name: str, channels: str):
    """A kernel manager whose kernel cannot collide with any other kernel.

    jupyter_client's default TCP transport picks the kernel's five ports in
    THIS process (bind to port 0, read the number, close the socket), writes
    them to the connection file, and the kernel binds them only later, in its
    own process. In between, the ports are free: a concurrently starting
    kernel (parallel CI, a batch of re-executions) can be handed the same
    number and the loser dies with ``ZMQError: Address already in use``.
    ``LocalPortCache`` only deduplicates within one process.

    The kernel's channels are therefore Unix-domain (``ipc``) sockets, named
    under ``channels`` — a fresh private directory of this call — so no other
    kernel can be handed the same address; the connection file lives there
    too. On Windows, where jupyter does not offer ``ipc`` kernels, the
    platform's only transport (tcp) is used as before.
    """
    from jupyter_client.manager import AsyncKernelManager

    if os.name == "nt":
        return AsyncKernelManager(kernel_name=kernel_name)
    return AsyncKernelManager(
        kernel_name=kernel_name,
        transport="ipc",
        ip=os.path.join(channels, "kernel"),
        connection_file=os.path.join(channels, "kernel.json"),
    )


# EOF
