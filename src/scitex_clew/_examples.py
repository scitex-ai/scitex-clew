#!/usr/bin/env python3
"""Create Clew example pipeline in a target directory."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional


def _find_examples_dir(variant: str = "sequential") -> Optional[Path]:
    """Locate the bundled Clew examples directory.

    Tries (in order):
    1. Source repo: ../../../examples/<variant>/   (editable install or git clone)
    2. Docker mount: /scitex-python/examples/scitex/clew
    """
    # __file__ = <repo>/src/scitex_clew/_examples.py — 3 parents up = <repo>.
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "examples" / variant,
        Path("/scitex-python/examples/scitex/clew") / variant,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def init_examples(dest: str | Path, variant: str = "sequential") -> dict:
    """Copy Clew example scripts to a destination directory.

    Copies only the runnable scripts (.py, .sh) and README — not
    the output directories.  Users run ``00_run_all.sh`` themselves
    to generate outputs and populate the verification database.

    Parameters
    ----------
    dest : str or Path
        Destination directory.  Created if it does not exist.
        Existing script files are overwritten.
    variant : str, optional
        Example variant: "sequential" (default) or "multi_parent".

    Returns
    -------
    dict
        ``{"path": str, "files": list[str], "file_count": int, "variant": str}``

    Raises
    ------
    FileNotFoundError
        If the bundled examples cannot be located.
    ValueError
        If variant is not recognized.
    """
    valid_variants = ("sequential", "multi_parent")
    if variant not in valid_variants:
        raise ValueError(f"Unknown variant {variant!r}. Choose from: {valid_variants}")

    src_dir = _find_examples_dir(variant)
    if src_dir is None:
        raise FileNotFoundError(
            f"Clew example variant {variant!r} not found. "
            "Examples live at ~/proj/scitex-clew/examples/<variant>/ — "
            "install editably (`pip install -e .`) or clone the repo."
        )

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Copy only scripts and docs, skip _out directories
    copied = []
    for src_file in sorted(src_dir.iterdir()):
        if src_file.is_dir():
            continue
        dst_file = dest / src_file.name
        shutil.copy2(src_file, dst_file)
        copied.append(src_file.name)

    return {
        "path": str(dest),
        "files": copied,
        "file_count": len(copied),
        "variant": variant,
    }


# EOF
