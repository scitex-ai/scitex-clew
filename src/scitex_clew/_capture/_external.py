#!/usr/bin/env python3
"""The capture boundary for EXTERNAL inputs: files a run reads from outside its project.

Real research reads data that does not live in the project tree: a shared
dataset (``/data``, ``/scratch``, a lab NAS mount, ``~/datasets``), a
downloaded file, a sibling project's outputs — often through a symlink inside
the project (``data/raw -> /mnt/shared/raw``). Such a read is a dependency of
every claim computed from it, but a slice can never BUNDLE it. The audit-hook
capture (:mod:`scitex_clew._capture`) therefore records it as an **external
input**: an ordinary ``input`` row (so ``slice`` / ``chain`` / ``verify``
follow it like any other input) whose ``external`` column carries
``{"via": <in-project path used, or null>, "size": <bytes>, "mtime": <epoch>}``.
The row's ``file_path`` is the absolute RESOLVED path and ``hash`` its content
hash (streamed, at read time — the bytes the run actually read).

Precision: what is NEVER recorded
---------------------------------
A Python process opens many files that are not data. :class:`ExternalPolicy`
excludes, by default (all paths compared after ``realpath``):

* the interpreter: ``sys.prefix`` / ``sys.exec_prefix`` / ``sys.base_prefix``
  / ``sys.base_exec_prefix``, every ``sysconfig`` install path (stdlib,
  platstdlib, purelib, platlib, include, scripts) and ``site`` /
  user-site packages;
* anything under a ``site-packages`` / ``dist-packages`` / ``__pycache__``
  directory, and Python sources/bytecode (``.py`` ``.pyc`` ``.pyo``);
* the directory of every imported top-level package (catches editable
  installs and package data such as matplotlib styles or bundled tables);
* system trees: ``/proc`` ``/sys`` ``/dev`` ``/etc`` ``/usr`` ``/lib*``
  ``/bin`` ``/sbin`` ``/boot`` ``/run`` ``/var`` ``/snap`` ``/nix`` ``/opt``
  (and the macOS ``/System`` ``/Library`` ``/private/{etc,var}``
  ``~/Library``);
* the temporary directory (:func:`tempfile.gettempdir`);
* clew/SciTeX state (``$SCITEX_DIR``, default ``~/.scitex``);
* hidden (dot) files and directories — ``~/.config``, ``~/.cache``,
  ``~/.local``, ``~/.netrc`` … are tool state, not data. A dot-directory
  that is an ANCESTOR of the project root (a project living under
  ``~/.worktrees/``) does not count;
* directories and anything that is not a regular file.

Configuration
-------------
``SCITEX_CLEW_EXTERNAL_INCLUDE`` / ``SCITEX_CLEW_EXTERNAL_EXCLUDE``
(``os.pathsep``-separated path prefixes) and, equivalently, the
``capture.external.include`` / ``capture.external.exclude`` lists of
``.scitex/clew/config.yaml``. An INCLUDE prefix overrides the built-in
exclusions above (e.g. data under ``/opt/lab-data`` or a downloads cache under
``~/.cache/huggingface``); an EXCLUDE prefix always wins. Set
``SCITEX_CLEW_EXTERNAL_CAPTURE=0`` (or ``capture.external.enabled: false``) to
stop recording external inputs — the in-project capture is unaffected, and the
run's ``metadata["capture"]["external"]`` says it was disabled.

Writes outside the root are NOT recorded as outputs (an output is what a
later run in THIS project consumes and what a slice bundles; a file written
elsewhere fits neither). They are remembered only so that reading such a file
back later in the same run is not mistaken for an external input.
"""

from __future__ import annotations

import os
import site
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Any

__all__ = [
    "ENV_EXTERNAL",
    "ENV_EXTERNAL_EXCLUDE",
    "ENV_EXTERNAL_INCLUDE",
    "ExternalPolicy",
    "external_capture_enabled",
    "is_under",
]

#: ``0`` / ``false`` / ``no`` / ``off`` stops recording external inputs.
ENV_EXTERNAL = "SCITEX_CLEW_EXTERNAL_CAPTURE"
#: ``os.pathsep``-separated prefixes recorded despite the built-in exclusions.
ENV_EXTERNAL_INCLUDE = "SCITEX_CLEW_EXTERNAL_INCLUDE"
#: ``os.pathsep``-separated prefixes never recorded as external inputs.
ENV_EXTERNAL_EXCLUDE = "SCITEX_CLEW_EXTERNAL_EXCLUDE"

_FALSY = {"0", "false", "no", "off"}

_SYSTEM_ROOTS = (
    "/proc",
    "/sys",
    "/dev",
    "/etc",
    "/usr",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/bin",
    "/sbin",
    "/boot",
    "/run",
    "/var",
    "/snap",
    "/nix",
    "/opt",
    "/System",
    "/Library",
    "/private/etc",
    "/private/var",
)
_LIBRARY_DIRS = frozenset({"site-packages", "dist-packages", "__pycache__"})
_CODE_SUFFIXES = (".py", ".pyc", ".pyo")


def is_under(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or lies below it (plain string paths)."""
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _split_env(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [p for p in raw.split(os.pathsep) if p.strip()]


def _config_external() -> dict[str, Any]:
    """``capture.external`` of the layered ``.scitex/clew`` config (or ``{}``)."""
    from .._core import load_config

    cfg = load_config()
    section = ((cfg.get("capture") or {}).get("external")) or {}
    if not isinstance(section, dict):
        raise ValueError(
            "clew config: capture.external must be a mapping "
            f"(got {type(section).__name__})"
        )
    return section


def external_capture_enabled(config: dict[str, Any] | None = None) -> bool:
    """False when env (or ``capture.external.enabled``) opts out."""
    env = os.environ.get(ENV_EXTERNAL)
    if env is not None:
        return env.strip().lower() not in _FALSY
    section = config if config is not None else {}
    enabled = section.get("enabled", True)
    return str(enabled).strip().lower() not in _FALSY


def _real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(str(path)))


def _interpreter_prefixes() -> set[str]:
    found: set[str] = set()
    for p in (sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix):
        if p:
            found.add(p)
    for key in ("stdlib", "platstdlib", "purelib", "platlib", "include", "scripts"):
        try:
            value = sysconfig.get_paths().get(key)
        except Exception:  # noqa: BLE001 - a broken sysconfig must not break open()
            value = None
        if value:
            found.add(value)
    try:
        found.update(site.getsitepackages())
    except AttributeError:  # virtualenv's legacy site module
        pass
    user_site = getattr(site, "getusersitepackages", lambda: None)()
    if user_site:
        found.add(user_site)
    return {_real(p) for p in found}


class ExternalPolicy:
    """Decide whether a resolved path outside the project root is a data input."""

    def __init__(
        self,
        project_root: str,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        enabled: bool | None = None,
    ):
        self.root = _real(project_root)
        config = _config_external()
        self.enabled = (
            external_capture_enabled(config) if enabled is None else bool(enabled)
        )
        self.include = [
            _real(p)
            for p in (
                include
                if include is not None
                else [*_split_env(ENV_EXTERNAL_INCLUDE), *(config.get("include") or [])]
            )
        ]
        self.exclude = [
            _real(p)
            for p in (
                exclude
                if exclude is not None
                else [*_split_env(ENV_EXTERNAL_EXCLUDE), *(config.get("exclude") or [])]
            )
        ]
        home = _real(str(Path.home()))
        builtin = set(_interpreter_prefixes())
        builtin.add(_real(tempfile.gettempdir()))
        builtin.add(
            _real(os.environ.get("SCITEX_DIR") or os.path.join(home, ".scitex"))
        )
        builtin.add(os.path.join(home, "Library"))
        builtin.update(_real(p) for p in _SYSTEM_ROOTS)
        builtin.update(p for p in _SYSTEM_ROOTS)
        # Never let a degenerate prefix ("/" or $HOME itself) swallow everything.
        self._builtin = sorted(p for p in builtin if p not in (os.sep, home))
        self._home = home
        self._package_dirs: list[str] = []
        self._modules_seen = -1

    # ------------------------------------------------------------- packages

    def _imported_package_dirs(self) -> list[str]:
        """Directories of imported top-level packages outside the project."""
        if len(sys.modules) == self._modules_seen:
            return self._package_dirs
        dirs: set[str] = set()
        for name, module in list(sys.modules.items()):
            if "." in name or module is None:
                continue
            try:
                attrs = vars(module)
            except TypeError:
                continue
            paths = attrs.get("__path__")
            if paths is None:
                continue  # a plain top-level module: its dir is a sys.path entry
            try:
                candidates = list(paths)
            except TypeError:
                continue
            for entry in candidates:
                real = _real(entry)
                if real in (os.sep, self._home) or is_under(self.root, real):
                    continue
                if not is_under(real, self.root):
                    dirs.add(real)
        self._package_dirs = sorted(dirs)
        self._modules_seen = len(sys.modules)
        return self._package_dirs

    # ------------------------------------------------------------- decision

    def _hidden(self, real: str) -> bool:
        try:
            common = os.path.commonpath([real, self.root])
        except ValueError:
            common = os.sep
        tail = real[len(common) :].lstrip(os.sep)
        return any(part.startswith(".") for part in tail.split(os.sep) if part)

    def builtin_excluded(self, real: str, *, code: bool = False) -> bool:
        """True when a built-in precision rule says ``real`` is not data.

        ``code=True`` judges a source file the run EXECUTED: ``.py`` is then
        allowed (bytecode never is); every library/system rule still applies.
        """
        if real.endswith((".pyc", ".pyo")) or (not code and real.endswith(".py")):
            return True
        if any(part in _LIBRARY_DIRS for part in real.split(os.sep)):
            return True
        if any(is_under(real, p) for p in self._builtin):
            return True
        if self._hidden(real):
            return True
        return any(is_under(real, p) for p in self._imported_package_dirs())

    def accepts(self, real: str, *, code: bool = False) -> bool:
        """True when the resolved outside-root path ``real`` is recorded."""
        if not self.enabled or is_under(real, self.root):
            return False
        if any(is_under(real, p) for p in self.exclude):
            return False
        if any(is_under(real, p) for p in self.include):
            return True
        return not self.builtin_excluded(real, code=code)

    def describe(self) -> dict[str, Any]:
        """The policy as recorded in ``metadata["capture"]["external"]``."""
        return {
            "enabled": self.enabled,
            "include": list(self.include),
            "exclude": list(self.exclude),
        }


def external_info(real: str, via: str | None) -> dict[str, Any]:
    """The ``external`` column payload for the external input ``real``."""
    try:
        st = os.stat(real)
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        size, mtime = None, None
    return {"via": via, "size": size, "mtime": mtime}


# EOF
