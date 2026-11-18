#!/usr/bin/env python3
"""A slice's software environment: what to install, and can it be installed?

Each kept run records ``packages`` (``{distribution: version}``) and, from
scitex-session 0.5.0, ``package_provenance``: per distribution, the PEP 610
install ``source`` (``index`` / ``editable`` / ``local_dir`` /
``local_archive`` / ``remote_archive`` / ``vcs``), a content ``fingerprint``
of the installed wheel and the installed files ``modified_files`` since
installation. A version alone cannot tell a locally patched build from the
index release; the provenance can.

:func:`merge_requirements` merges the runs' records into what a re-run must
install (``ProvenanceSlice.requirements()``). :func:`environment_findings`
says which of those requirements are NOT reproducible from the record:

``not_from_index``
    installed from a local directory, a local archive, an editable source,
    a VCS URL or a remote archive — ``pip install <dist>==<version>`` from
    the index installs something else (or nothing).
``edited_after_install``
    an index install whose files were edited (or overwritten / deleted)
    after installation: the version and fingerprint still match the release,
    the code that ran did not.
``content_differs``
    the same version is installed HERE with a different fingerprint: this
    environment holds other code under the recorded name and version (the
    recorded build was patched/rebuilt, or this one is).
``edited_here``
    the same version and fingerprint are installed here, but files of this
    installation were edited after it was installed.

The fingerprint scheme is shared with scitex-session (``record-sha256-v1``,
see ``scitex_session._lifecycle._dist_provenance``); clew re-implements it
because it has no runtime dependency on scitex-session, and its tests check
both implementations agree on real installed distributions.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

__all__ = [
    "FINGERPRINT_SCHEME",
    "current_distribution",
    "environment_findings",
    "merge_requirements",
    "non_reproducible_reason",
    "record_fingerprint",
]

FINGERPRINT_SCHEME = "record-sha256-v1"
_INSTALLER_FILES = frozenset({"INSTALLER", "REQUESTED", "direct_url.json", "RECORD"})
_CHUNK = 1 << 20


# ---------------------------------------------------------------------------
# Fingerprint (record-sha256-v1) — identical to scitex-session's
# ---------------------------------------------------------------------------


def _record_rows(record: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in record.splitlines():
        parts = line.rsplit(",", 2)
        if len(parts) != 3:
            continue
        path, digest, size = parts
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1].replace('""', '"')
        rows.append((path, digest, size))
    return rows


def _fingerprinted(path: str) -> bool:
    if path.startswith("..") or path.startswith("/"):
        return False
    parts = path.split("/")
    if "__pycache__" in parts or path.endswith((".pyc", ".pyo")):
        return False
    return not (
        len(parts) == 2
        and parts[0].endswith(".dist-info")
        and parts[1] in _INSTALLER_FILES
    )


def record_fingerprint(record: str) -> str | None:
    """``"sha256:<hex>"`` over the wheel-shipped ``RECORD`` entries."""
    lines = sorted(
        f"{path},{digest}"
        for path, digest, _size in _record_rows(record)
        if digest and _fingerprinted(path)
    )
    if not lines:
        return None
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _file_digest(path: str, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode("ascii")


def _modified_files(dist, record: str) -> list[str]:
    base = str(dist.locate_file(""))
    try:
        record_mtime = os.stat(Path(dist._path) / "RECORD").st_mtime_ns
    except (AttributeError, OSError, TypeError):
        record_mtime = None
    modified: list[str] = []
    for path, recorded, size in _record_rows(record):
        if not recorded or not _fingerprinted(path):
            continue
        full = os.path.join(base, path)
        try:
            st = os.stat(full)
        except FileNotFoundError:
            modified.append(path)
            continue
        size_differs = size.isdigit() and int(size) != st.st_size
        newer = record_mtime is not None and st.st_mtime_ns > record_mtime
        if not (size_differs or newer):
            continue
        algorithm, _, expected = recorded.partition("=")
        try:
            if size_differs or _file_digest(full, algorithm) != expected:
                modified.append(path)
        except (OSError, ValueError):
            modified.append(path)
    return sorted(modified)


def current_distribution(name: str, cache: dict | None = None) -> dict | None:
    """``{"version", "fingerprint", "modified_files"}`` of ``name`` as
    installed in THIS interpreter's environment (None when not installed)."""
    if cache is not None and name in cache:
        return cache[name]
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        dist = distribution(name)
    except PackageNotFoundError:
        state = None
    else:
        record = dist.read_text("RECORD") or ""
        direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
        editable = bool((direct_url.get("dir_info") or {}).get("editable"))
        state = {
            "version": dist.version,
            "fingerprint": None if editable else record_fingerprint(record),
            "modified_files": []
            if editable or not record
            else _modified_files(dist, record),
        }
    if cache is not None:
        cache[name] = state
    return state


# ---------------------------------------------------------------------------
# Requirements of a slice
# ---------------------------------------------------------------------------


def non_reproducible_reason(info: dict) -> tuple[str, str] | None:
    """``(kind, message)`` when a recorded distribution cannot be re-installed
    from its record (see module doc), else None."""
    source = info.get("source")
    if source not in (None, "index"):
        where = info.get("url") or "?"
        if source == "vcs" and info.get("commit_id"):
            where = f"{where}@{info['commit_id']}"
        return (
            "not_from_index",
            f"installed from {str(source).replace('_', ' ')} ({where}), not a "
            "package index: the index release of this version is other code",
        )
    modified = info.get("modified_files") or []
    if modified:
        total = info.get("modified_files_truncated") or len(modified)
        return (
            "edited_after_install",
            f"{total} installed file(s) edited, overwritten or deleted after "
            f"installation (e.g. {modified[0]}): the index release differs "
            "from the code that ran",
        )
    return None


def merge_requirements(runs, environment: dict) -> dict:
    """What a re-run of ``runs`` must install (``ProvenanceSlice.requirements``).

    ``packages`` maps each distribution to its version (one version);
    ``conflicts`` lists distributions whose runs recorded different
    versions; ``unresolved_imports`` is imported code no distribution owns;
    ``runs_without_environment`` are kept runs that recorded no packages.
    ``provenance`` maps each distribution to its recorded install
    provenance records (one per distinct record, with the ``runs`` that
    recorded it); ``runs_without_provenance`` recorded packages but no
    provenance (scitex-session < 0.5.0) — their packages cannot be checked.
    """
    versions: dict[str, set[str]] = {}
    unresolved: dict[str, str] = {}
    provenance: dict[str, list[dict]] = {}
    missing: list[str] = []
    without_provenance: list[str] = []
    for sid in runs:
        env = environment.get(sid)
        if not env or env.get("packages") is None:
            missing.append(sid)
            continue
        for dist, version in (env.get("packages") or {}).items():
            versions.setdefault(dist, set()).add(str(version))
        unresolved.update(env.get("unresolved_imports") or {})
        recorded = env.get("package_provenance")
        if recorded is None:
            without_provenance.append(sid)
            continue
        for dist, info in recorded.items():
            if not isinstance(info, dict):
                continue
            entries = provenance.setdefault(dist, [])
            same = next((e for e in entries if _same_record(e, info)), None)
            if same is None:
                entries.append({**info, "runs": [sid]})
            elif sid not in same["runs"]:
                same["runs"].append(sid)
    return {
        "packages": {
            d: sorted(v)[0] for d, v in sorted(versions.items()) if len(v) == 1
        },
        "conflicts": {d: sorted(v) for d, v in sorted(versions.items()) if len(v) > 1},
        "unresolved_imports": dict(sorted(unresolved.items())),
        "runs_without_environment": missing,
        "provenance": dict(sorted(provenance.items())),
        "runs_without_provenance": without_provenance,
    }


def _same_record(a: dict, b: dict) -> bool:
    keys = ("version", "source", "url", "fingerprint", "modified_files")
    return all(a.get(k) == b.get(k) for k in keys)


def environment_findings(
    requirements: dict, *, check_current: bool = True, cache: dict | None = None
) -> list[dict]:
    """Non-reproducible environment requirements of a slice (see module doc).

    One dict per finding: ``{"distribution", "version", "kind", "message",
    "runs"}``. ``check_current`` also compares each recorded fingerprint with
    the same version installed in this interpreter's environment; ``cache``
    (``{name: state}``) shares those lookups across slices in one pass.
    """
    findings: list[dict] = []
    for dist, entries in (requirements.get("provenance") or {}).items():
        for info in entries:
            base = {
                "distribution": dist,
                "version": info.get("version"),
                "runs": list(info.get("runs") or []),
            }
            reason = non_reproducible_reason(info)
            if reason is not None:
                findings.append({**base, "kind": reason[0], "message": reason[1]})
            if not check_current or not info.get("fingerprint"):
                continue
            if info.get("fingerprint_scheme", FINGERPRINT_SCHEME) != FINGERPRINT_SCHEME:
                continue
            here = current_distribution(dist, cache)
            if here is None or here["version"] != info.get("version"):
                continue  # not a same-version comparison: version drift
            if here["fingerprint"] != info["fingerprint"]:
                findings.append(
                    {
                        **base,
                        "kind": "content_differs",
                        "message": (
                            f"the {dist}=={here['version']} installed here has "
                            f"other content (fingerprint {here['fingerprint']}) "
                            f"than the one the run used ({info['fingerprint']}): "
                            "same name and version, different code"
                        ),
                    }
                )
            elif here["modified_files"] and not info.get("modified_files"):
                findings.append(
                    {
                        **base,
                        "kind": "edited_here",
                        "message": (
                            f"{len(here['modified_files'])} file(s) of the "
                            f"{dist} installed here were edited after "
                            f"installation (e.g. {here['modified_files'][0]})"
                        ),
                    }
                )
    return findings


# EOF
