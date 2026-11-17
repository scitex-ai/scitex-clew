#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_tracker.py
"""Session tracker for automatic verification."""

from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ._db import get_db
from ._db._file_hashes import _stat_size
from ._hash import combine_hashes, hash_file
from ._tracker_batch import _explicit_external, warn_external_inputs
from ._tracker_batch import explicit_links, note_links, write_links
from ._tracker_batch import record_hashed_inputs as _record_hashed_inputs
from ._tracker_batch import relocate as _relocate


class SessionTracker:
    """
    Track inputs/outputs during a session for verification.

    Automatically records file hashes when files are loaded or saved
    through stx.io, and stores them in the verification database.

    Examples
    --------
    >>> tracker = SessionTracker("2025Y-11M-18D-09h12m03s_HmH5")
    >>> tracker.record_input("data.csv")
    >>> tracker.record_output("result.png")
    >>> tracker.finalize()
    """

    def __init__(
        self,
        session_id: str,
        script_path: str | None = None,
        parent_session: str | None = None,
        metadata: dict[str, Any] | None = None,
        db=None,
    ):
        """
        Initialize a session tracker.

        Parameters
        ----------
        session_id : str
            Unique session identifier
        script_path : str, optional
            Path to the script being run
        parent_session : str, optional
            Parent session ID for chain tracking
        metadata : dict, optional
            Additional metadata (e.g. notebook_path, cell_index)
        db : VerificationDB, optional
            Database instance to use.  Defaults to the global DB instance.
        """
        self.session_id = session_id
        self.script_path = script_path
        self.parent_session = parent_session

        self._inputs: dict[str, str] = {}
        #: resolved path -> ``external`` payload of inputs read from OUTSIDE
        #: the project root (see :mod:`scitex_clew._capture._external`).
        self._external: dict[str, dict] = {}
        self._outputs: dict[str, str] = {}
        #: link path -> in-project symlink traversed to a recorded file (#192).
        self._links: dict[str, dict] = {}
        # path -> (hash, declared derived_from) of outputs recorded WITH a
        # declaration, so a same-bytes re-record cannot erase it.
        self._declared: dict[str, tuple[str, list[str]]] = {}
        self._script_hash: str | None = None
        self._finalized = False
        self._parent_sessions: set = set()
        if parent_session:
            self._parent_sessions.add(parent_session)

        self._db = db if db is not None else get_db()

        # Compute script hash if provided
        if script_path and Path(script_path).exists():
            self._script_hash = hash_file(script_path)

        # Register run in database
        self._db.add_run(
            session_id=session_id,
            script_path=script_path or "",
            script_hash=self._script_hash,
            parent_session=parent_session,
            metadata=metadata,
        )

    def record_input(
        self,
        path: str | Path,
        track: bool = True,
    ) -> str | None:
        """
        Record a file as an input.

        Parameters
        ----------
        path : str or Path
            Path to the input file
        track : bool, optional
            Whether to track this file (default: True)

        Returns
        -------
        str or None
            Hash of the file, or None if not tracked
        """
        if not track or self._finalized:
            return None

        path = Path(path)
        if not path.exists():
            return None

        path_str = str(path.resolve())
        self.note_links(explicit_links(path, path_str))
        if path_str not in self._inputs:
            file_hash = hash_file(path)
            self._inputs[path_str] = file_hash
            external = _explicit_external(path)
            if external is not None:
                self._external[path_str] = external
            self._db.add_file_hash(
                session_id=self.session_id,
                file_path=path_str,
                hash_value=file_hash,
                role="input",
                size_bytes=_stat_size(path_str),
                external=external,
            )

            # Auto-link the parent: the producer of THESE bytes (content hash),
            # never every session that ever wrote this path. Same binding rule
            # as the lineage resolver (scitex_clew._chain._routes); at load
            # time every recorded output precedes this input, so no time gate.
            from ._chain._routes import bind_input

            producers = self._db.find_producer_records([path_str]).get(path_str, [])
            producer = bind_input(
                producers,
                consumer_session=self.session_id,
                input_hash=file_hash,
            )
            if producer is not None and producer not in self._parent_sessions:
                self._parent_sessions.add(producer)
                self._db.add_parent(self.session_id, producer)
                if self.parent_session is None:
                    self.parent_session = producer

        return self._inputs[path_str]

    #: Bulk counterpart of :meth:`record_input` for pre-hashed paths.
    record_hashed_inputs = _record_hashed_inputs
    #: Apply a session manager's run-dir move (``relocations``) to the record.
    relocate = _relocate
    #: Remember in-project symlinks traversed to recorded files (#192).
    note_links = note_links

    def record_output(
        self,
        path: str | Path,
        track: bool = True,
        derived_from: list[str | Path] | None = None,
    ) -> str | None:
        """
        Record a file as an output.

        Parameters
        ----------
        path : str or Path
            Path to the output file
        track : bool, optional
            Whether to track this file (default: True)
        derived_from : list of str or Path, optional
            The files this output was computed from (inputs of this run, or
            earlier outputs of it). Declaring it lets the level-2 minimal
            slice (:func:`scitex_clew.slice`) drop this run's other inputs
            from the output's back-trace. ``None`` = undeclared (the slice
            keeps every input of the run). An empty list declares "derived
            from no file".

            Recording the SAME bytes of the same path again in this run
            (e.g. a figure tool records its image, then the ``stx.io.save``
            that called it fires its hook for the same file) never erases a
            declaration: an undeclared re-record keeps it and a second
            declaration is unioned with it. New bytes replace it.

        Returns
        -------
        str or None
            Hash of the file, or None if not tracked
        """
        if not track or self._finalized:
            return None

        path = Path(path)
        if not path.exists():
            return None

        path_str = str(path.resolve())
        file_hash = hash_file(path)
        self._outputs[path_str] = file_hash
        self.note_links(explicit_links(path, path_str))
        declared = (
            None
            if derived_from is None
            else [str(Path(p).resolve()) for p in derived_from]
        )
        declared = self._merge_declaration(path_str, file_hash, declared)
        self._db.add_file_hash(
            session_id=self.session_id,
            file_path=path_str,
            hash_value=file_hash,
            role="output",
            size_bytes=_stat_size(path_str),
            derived_from=declared,
        )

        return file_hash

    def _merge_declaration(
        self, path_str: str, file_hash: str, declared: list[str] | None
    ) -> list[str] | None:
        """Combine ``declared`` with an earlier declaration of the same bytes."""
        previous = self._declared.get(path_str)
        if previous is not None and previous[0] == file_hash:
            if declared is None:
                return list(previous[1])
            declared = previous[1] + [p for p in declared if p not in previous[1]]
        if declared is None:
            self._declared.pop(path_str, None)
        else:
            self._declared[path_str] = (file_hash, list(declared))
        return declared

    def record_inputs(
        self,
        paths: list[str | Path],
        track: bool = True,
    ) -> dict[str, str]:
        """Record multiple input files."""
        result = {}
        for path in paths:
            h = self.record_input(path, track=track)
            if h:
                result[str(path)] = h
        return result

    def record_outputs(
        self,
        paths: list[str | Path],
        track: bool = True,
    ) -> dict[str, str]:
        """Record multiple output files."""
        result = {}
        for path in paths:
            h = self.record_output(path, track=track)
            if h:
                result[str(path)] = h
        return result

    @property
    def inputs(self) -> dict[str, str]:
        """Get all recorded inputs."""
        return self._inputs.copy()

    @property
    def outputs(self) -> dict[str, str]:
        """Get all recorded outputs."""
        return self._outputs.copy()

    @property
    def combined_hash(self) -> str:
        """Get combined hash of all inputs, script, and outputs."""
        all_hashes = {}
        all_hashes.update({f"input:{k}": v for k, v in self._inputs.items()})
        if self._script_hash:
            all_hashes["script"] = self._script_hash
        all_hashes.update({f"output:{k}": v for k, v in self._outputs.items()})
        return combine_hashes(all_hashes)

    def finalize(
        self,
        status: str = "success",
        exit_code: int = 0,
    ) -> dict[str, Any]:
        """
        Finalize the session tracking.

        Parameters
        ----------
        status : str, optional
            Final status (success, failed, error)
        exit_code : int, optional
            Exit code of the script

        Returns
        -------
        dict
            Summary of the tracked session
        """
        if self._finalized:
            return self.summary()

        combined = self.combined_hash
        warn_external_inputs(self.session_id, self._external)
        write_links(self)

        self._db.finish_run(
            session_id=self.session_id,
            status=status,
            exit_code=exit_code,
            combined_hash=combined,
        )

        self._finalized = True

        return self.summary()

    def summary(self) -> dict[str, Any]:
        """Get summary of tracked files."""
        return {
            "session_id": self.session_id,
            "script_path": self.script_path,
            "script_hash": self._script_hash,
            "parent_session": self.parent_session,
            "inputs": self._inputs,
            "outputs": self._outputs,
            "combined_hash": self.combined_hash,
            "finalized": self._finalized,
        }


# Global tracker for current session
_CURRENT_TRACKER: SessionTracker | None = None


def get_tracker() -> SessionTracker | None:
    """Get the current session tracker."""
    return _CURRENT_TRACKER


def set_tracker(tracker: SessionTracker | None) -> None:
    """Set the current session tracker."""
    global _CURRENT_TRACKER
    _CURRENT_TRACKER = tracker


def start_tracking(
    session_id: str,
    script_path: str | None = None,
    parent_session: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SessionTracker:
    """
    Start tracking a new session.

    Parameters
    ----------
    session_id : str
        Unique session identifier
    script_path : str, optional
        Path to the script being run
    parent_session : str, optional
        Parent session ID for chain tracking
    metadata : dict, optional
        Additional metadata (e.g. notebook_path, cell_index)

    Returns
    -------
    SessionTracker
        The new tracker instance
    """
    tracker = SessionTracker(
        session_id=session_id,
        script_path=script_path,
        parent_session=parent_session,
        metadata=metadata,
    )
    set_tracker(tracker)
    return tracker


def stop_tracking(
    status: str = "success",
    exit_code: int = 0,
) -> dict[str, Any] | None:
    """
    Stop tracking the current session.

    Parameters
    ----------
    status : str, optional
        Final status
    exit_code : int, optional
        Exit code

    Returns
    -------
    dict or None
        Summary of the tracked session, or None if no tracker
    """
    tracker = get_tracker()
    if tracker is None:
        return None

    result = tracker.finalize(status=status, exit_code=exit_code)
    set_tracker(None)
    return result


@contextmanager
def session(
    script_path: str | None = None,
    session_id: str | None = None,
    parent_session: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Zero-dependency provenance-recording context manager.

    Records a REAL run in the clew DB — the ``runs`` row plus the
    ``input -> output`` file-hash edges — using ONLY clew's pure-stdlib core.
    So it works in stripped environments where ``import scitex`` / the
    ``@stx.session`` decorator cannot load (no numpy/h5py/matplotlib/system
    libs), giving a minimal-mode script a way to produce ``runs >= 1`` and a
    source-reachable DAG that passes the provenance gate.

    Inside the block, call ``run.record_input(path)`` / ``run.record_output(path)``
    (or the module-level :func:`record_input` / :func:`record_output`, which act
    on the current session) to hash + link files. A claim registered against a
    recorded OUTPUT then grounds through the recorded run to whatever registered
    source feeds it.

    This is clew's OWN recorder — it does NOT import scitex-session; it is the
    zero-dep counterpart to ``@stx.session`` (the full-stack path), sharing the
    same ``runs`` / ``file_hashes`` tables. Use one or the other per run, not both.

    Parameters
    ----------
    script_path : str, optional
        Path to the script being run. Defaults to ``sys.argv[0]`` (the invoking
        script) when not given.
    session_id : str, optional
        Unique run id. A random hex id is generated when omitted.
    parent_session : str, optional
        Explicit parent run id (parents are also auto-linked from inputs).
    metadata : dict, optional
        Extra run metadata.

    Yields
    ------
    SessionTracker
        The active tracker; call ``.record_input`` / ``.record_output`` on it.

    Examples
    --------
    >>> import scitex_clew as clew
    >>> with clew.session(script_path=__file__) as run:
    ...     run.record_input("data/raw.csv")
    ...     # ... stdlib compute; write results/out.json with open()/json ...
    ...     run.record_output("results/out.json")
    ...     clew.add_claim("paper.tex", "value", 42, "0.94",
    ...                    source_file="results/out.json")
    """
    sid = session_id or uuid.uuid4().hex
    spath = script_path if script_path is not None else (sys.argv[0] or None)
    start_tracking(
        sid,
        script_path=spath,
        parent_session=parent_session,
        metadata=metadata,
    )
    status, exit_code = "success", 0
    try:
        yield get_tracker()
    except BaseException:
        status, exit_code = "error", 1
        raise
    finally:
        stop_tracking(status=status, exit_code=exit_code)


# Module-level conveniences live with the other tracker helpers; re-exported
# here because ``clew.record_input`` / ``record_output`` resolve to this module.
from ._tracker_batch import record_input, record_output  # noqa: E402, F401


# EOF
