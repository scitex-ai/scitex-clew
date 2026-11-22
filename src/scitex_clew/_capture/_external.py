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
* files in the temporary directory that THIS PROCESS TREE made (see
  "Temporary directories" below);
* clew/SciTeX state (``$SCITEX_DIR``, default ``~/.scitex``);
* hidden (dot) files and directories — ``~/.config``, ``~/.cache``,
  ``~/.local``, ``~/.netrc`` … are tool state, not data. A dot-directory
  that is an ANCESTOR of the project root (a project living under
  ``~/.worktrees/``) does not count;
* directories and anything that is not a regular file.

Temporary directories
---------------------
A temp root is :func:`tempfile.gettempdir` (``$TMPDIR``), ``/tmp`` and
``/var/tmp`` (each also by ``realpath``). Most of what a run touches there is
its own churn — scratch files it writes and reads back, a library's
per-process cache (matplotlib's fallback config dir, a Jupyter kernel's cell
files) — and is never an input. But a file that ALREADY EXISTED when the
process started (a scratch dir or symlink a shell command made by hand, a
download a wrapper script staged) is real state the run depends on, and a
replay without it fails. So the rule is by ORIGIN, not by name:

  a regular file under a temp root is recorded as an external input iff its
  ``max(mtime, ctime)`` is older than THIS PROCESS's start time — it
  pre-existed the process and nothing in the process tree (this process or
  a child it spawned) created, rewrote, copied or renamed it since.

Process start is read from ``/proc/self/stat`` on Linux (clock-tick
precision; the threshold is the tick AFTER the reported start, so a file
made by the launching shell an instant before the exec still counts as
pre-existing). Elsewhere it falls back to the time clew was imported, which
can only make more files count as pre-existing — a louder record, never a
silent hole. Files this process writes are additionally remembered (see
below), and all other precision rules (bytecode, ``__pycache__``, hidden
names below the temp root, imported packages) still apply. Limitation: a file
an UNRELATED process creates in temp while this process runs looks like the
process tree's own and is not recorded.

A symlink located under a temp root (not the root itself) that the run went
through, and that pre-existed the process (``lstat``), is recorded like an
in-project link (:mod:`scitex_clew._links`) with ``"external": true``:
``verify`` reports it gone as a missing EXTERNAL input (``EXTERNAL_MISSING``),
and a slice lists it for recreation at its absolute path.

Configuration
-------------
``SCITEX_CLEW_EXTERNAL_INCLUDE`` / ``SCITEX_CLEW_EXTERNAL_EXCLUDE``
(``os.pathsep``-separated path prefixes) and, equivalently, the
``capture.external.include`` / ``capture.external.exclude`` lists of
``.scitex/clew/config.yaml``. An INCLUDE prefix overrides the built-in
exclusions above (e.g. data under ``/opt/lab-data`` or a downloads cache under
``~/.cache/huggingface``); an EXCLUDE prefix always wins. An INCLUDE prefix
under a temp root records every file there, pre-existing or not; an EXCLUDE
of ``$TMPDIR`` (or ``/tmp``) restores the old "temp is never data" behaviour.
Set
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
import time
from pathlib import Path
from typing import Any

__all__ = [
    "ENV_EXTERNAL",
    "ENV_EXTERNAL_EXCLUDE",
    "ENV_EXTERNAL_INCLUDE",
    "ExternalPolicy",
    "external_capture_enabled",
    "is_under",
    "process_start_time",
    "temp_roots",
]

#: Fallback process-start estimate where ``/proc`` is unavailable: the moment
#: clew was imported (later than the true start, so it errs towards recording).
_IMPORTED_AT = time.time()
_START_CACHE: dict[int, float] = {}

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


def _linux_process_start() -> float | None:
    """Wall-clock epoch just AFTER this process started, from ``/proc``.

    ``/proc/self/stat`` field 22 is the start time in clock ticks since boot;
    the elapsed time is measured on ``CLOCK_BOOTTIME`` (immune to wall-clock
    steps) and subtracted from now. The reported start is floored to a tick,
    so one tick is added: a file the launching shell wrote an instant before
    the exec must not be mistaken for this process's own.
    """
    boottime = getattr(time, "CLOCK_BOOTTIME", None)
    if boottime is None:
        return None
    try:
        with open("/proc/self/stat", "rb") as f:
            stat = f.read().decode("ascii", "replace")
        ticks = os.sysconf("SC_CLK_TCK")
        # Fields after the parenthesised comm (which may itself hold spaces).
        start_ticks = int(stat[stat.rindex(")") + 2 :].split()[19])
        now_boot = time.clock_gettime(boottime)
        now_wall = time.time()
    except (OSError, ValueError, IndexError):
        return None
    return now_wall - (now_boot - start_ticks / ticks) + 1.0 / ticks


def process_start_time() -> float:
    """Epoch threshold below which a file pre-existed THIS process.

    Linux: ``/proc/self/stat`` (see :func:`_linux_process_start`). Elsewhere:
    the time clew was imported — later than the true start, which can only
    make MORE temp files count as pre-existing (recorded), never fewer.
    """
    pid = os.getpid()
    cached = _START_CACHE.get(pid)
    if cached is None:
        cached = _START_CACHE[pid] = _linux_process_start() or _IMPORTED_AT
    return cached


def temp_roots() -> list[str]:
    """The temp roots: ``$TMPDIR`` / :func:`tempfile.gettempdir`, ``/tmp``,
    ``/var/tmp`` — each as given and by ``realpath`` (``/tmp`` is a symlink
    to ``/private/tmp`` on macOS)."""
    roots: set[str] = set()
    for p in (tempfile.gettempdir(), "/tmp", "/var/tmp"):
        roots.add(os.path.abspath(p))
        roots.add(_real(p))
    return sorted(r for r in roots if r != os.sep)


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
        temp: list[str] | None = None,
        process_start: float | None = None,
    ):
        self.root = _real(project_root)
        #: Temp roots (see "Temporary directories" in the module doc).
        self.temp_roots = sorted(
            {_real(p) for p in temp} | {os.path.abspath(p) for p in temp}
            if temp is not None
            else temp_roots()
        )
        #: Files under a temp root older than this pre-existed the process.
        self.process_start = (
            process_start if process_start is not None else process_start_time()
        )
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
        self._interpreter = sorted(
            path for path in _interpreter_prefixes() if path not in (os.sep, home)
        )
        builtin = {
            _real(os.environ.get("SCITEX_DIR") or os.path.join(home, ".scitex")),
            os.path.join(home, "Library"),
        }
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

    def temp_root_of(self, path: str) -> str | None:
        """The temp root ``path`` lies STRICTLY below, else None."""
        for root in self.temp_roots:
            if path != root and is_under(path, root):
                return root
        return None

    def _hidden(self, real: str, base: str | None = None) -> bool:
        """A dot-named component below ``base`` (default: the deepest common
        ancestor of ``real`` and the project root)."""
        if base is None:
            try:
                base = os.path.commonpath([real, self.root])
            except ValueError:
                base = os.sep
        tail = real[len(base) :].lstrip(os.sep)
        return any(part.startswith(".") for part in tail.split(os.sep) if part)

    def builtin_excluded(self, real: str, *, code: bool = False) -> bool:
        """True when a built-in precision rule says ``real`` is not data.

        ``code=True`` judges a source file the run EXECUTED: ``.py`` is then
        allowed (bytecode never is); every library/system rule still applies.
        A path under a temp root is judged by the temp rule instead of the
        system-tree prefixes (``/var/tmp`` is under ``/var``; macOS keeps
        ``$TMPDIR`` under ``/private/var``), and only names hidden BELOW the
        temp root count as hidden (``$TMPDIR`` may itself sit under a dot-dir).
        """
        if real.endswith((".pyc", ".pyo")) or (not code and real.endswith(".py")):
            return True
        if any(part in _LIBRARY_DIRS for part in real.split(os.sep)):
            return True
        if any(is_under(real, path) for path in self._interpreter):
            return True
        temp = self.temp_root_of(real)
        if temp is None and any(is_under(real, p) for p in self._builtin):
            return True
        if self._hidden(real, temp):
            return True
        return any(is_under(real, p) for p in self._imported_package_dirs())

    def preexisting(self, path: str, *, follow: bool = True) -> bool:
        """True when ``path`` existed, unchanged, since before this process.

        ``max(mtime, ctime)`` must predate :attr:`process_start`: a file this
        process or any child created, rewrote, copied (``cp -p`` keeps mtime,
        not ctime) or renamed since is the process tree's own. ``follow=False``
        judges a symlink itself.
        """
        try:
            st = os.stat(path) if follow else os.lstat(path)
        except OSError:
            return False
        return max(st.st_mtime, st.st_ctime) < self.process_start

    def accepts(self, real: str, *, code: bool = False) -> bool:
        """True when the resolved outside-root path ``real`` is recorded."""
        if not self.enabled or is_under(real, self.root):
            return False
        if any(is_under(real, p) for p in self.exclude):
            return False
        if any(is_under(real, p) for p in self.include):
            return True
        if self.builtin_excluded(real, code=code):
            return False
        if self.temp_root_of(real) is not None:
            return self.preexisting(real)
        return True

    def records_link(self, link: str) -> bool:
        """True when a symlink OUTSIDE the project is part of the record.

        Links elsewhere on the machine (``/home -> /mnt/home``) are the host's
        layout, not the run's. A link under a temp root that pre-existed the
        process is hand-made state the run went through (``/tmp/x/data ->
        ...``): a replay needs it, so it is recorded (see module doc).
        """
        if not self.enabled or is_under(link, self.root):
            return False
        if any(is_under(link, p) for p in self.exclude):
            return False
        temp = self.temp_root_of(link)
        if temp is None or self._hidden(link, temp):
            return False
        return self.preexisting(link, follow=False)

    def describe(self) -> dict[str, Any]:
        """The policy as recorded in ``metadata["capture"]["external"]``."""
        return {
            "enabled": self.enabled,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "temp": {
                "roots": list(self.temp_roots),
                "rule": "pre-existing",
                "process_start": self.process_start,
            },
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
