#!/usr/bin/env python3
"""Who is opening this file? Call-stack checks for :mod:`scitex_clew._capture`.

The audit hook sees every ``open`` of the process. Some opens under the
project root are not data reads of the run even though the run's thread made
them; this module tells them apart by the modules on the call stack.
"""

from __future__ import annotations

import sys

__all__ = ["not_a_run_read"]

#: Modules whose frames mean "a ``scitex_io.save`` is in progress".
_STX_IO_SAVE_MODULES = ("scitex_io._save",)
#: clew's own capture machinery: its frames sit under every hooked open.
_CAPTURE_PACKAGE = __name__.rsplit(".", 1)[0]  # "scitex_clew._capture"
_CLEW_PACKAGE = _CAPTURE_PACKAGE.split(".", 1)[0]  # "scitex_clew"


def _is_clew_module(name: str) -> bool:
    """True for clew's own modules, except the capture machinery itself."""
    if not (name == _CLEW_PACKAGE or name.startswith(_CLEW_PACKAGE + ".")):
        return False
    return not (name == _CAPTURE_PACKAGE or name.startswith(_CAPTURE_PACKAGE + "."))


def not_a_run_read(depth: int = 2) -> str | None:
    """Why the current ``open()`` is not a data read of the run, else None.

    * ``"stx-io-save"`` — inside ``scitex_io.save``: a saver may read its own
      target before overwriting it (the CSV saver compares with the existing
      file to skip identical writes). Recording it would bind the run to
      whichever earlier run produced the old bytes, an invented edge. The
      save's real effect is reported by scitex-io's post-save hook.
    * ``"clew"`` — inside clew's own code (``add_claim``, ``verify_claim``,
      ``verify_all_claims``, ``verify_run`` / ``verify_chain``, ...).
      Verification re-hashes every file of a claim's upstream chain. Done
      inside a session (a validity gate at the end of a script), those reads
      would make the verifying session depend on its whole upstream closure:
      invented edges that defeat a minimal DAG. A file the run really uses is
      opened by the run's own code and recorded there.

    ``depth`` skips the caller's own frames. Walk this only for the first
    read of an in-scope path, so the cost stays off the hot path.
    """
    frame = sys._getframe(depth)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name.startswith(_STX_IO_SAVE_MODULES):
            return "stx-io-save"
        if _is_clew_module(name):
            return "clew"
        frame = frame.f_back
    return None


# EOF
