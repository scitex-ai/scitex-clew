#!/usr/bin/env python3
"""Read-back rewrites: which run a SLICE credits with a file's content.

The defect (paper E2 minimality run)
------------------------------------
A script ran twice. Each run READ its output path ``F`` and then REWROTE ``F``
with the identical bytes ``h``. The second run's input row ``F@h`` binds (by
hash, :mod:`._routes`) to the first run's output, so the level-1 slice of
``F@h`` held BOTH runs; ablation showed either one alone reproduces the claim.

The rule (content-addressed)
----------------------------
A claim needs CONTENT ``h``, not a particular writer of it. A run ``R`` that
read ``P`` at hash ``h`` and recorded ``P`` as an output with that same hash
``h`` left ``P`` exactly as it found it: as far as ``P`` is concerned ``R`` is
a no-op, and the bytes were already there because of the producer ``R``'s
read is bound to. So when a slice demands ``P`` from ``R``, it asks that
producer instead, and repeats while the producer is itself such a rewrite.
The run credited is the ORIGINATING producer: the earliest run in the
read-back chain, i.e. the one whose ``P`` input had different bytes (or that
did not read ``P`` at all, or whose read binds to no recorded producer).

Why the earliest and not the latest rewriter: level 1 is conservative WITHIN a
run (Clew cannot see which input an output came from), so it cannot assume the
latest run's ``P`` was computed without reading ``P`` — a ``load(P); save(P)``
script needs the earlier bytes. The originating producer needs no such
assumption: by the recorded timeline ``P`` already held ``h`` once it had run,
so it and its own ancestors are sufficient for ``P@h`` whatever the later
rewriters did internally. The choice is deterministic because the read
binding is (newest producer of those bytes recorded before the read).

Scope
-----
* Only the PRODUCER OF A DEMANDED OUTPUT changes. A run that is kept for
  another reason keeps ALL its inputs (level 1) and their producers: if run 2
  read ``F@h`` and also wrote ``G``, the slice of ``G`` keeps run 2, its input
  ``F@h`` and run 1 (in a fresh re-run ``F`` must exist before run 2 opens
  it). Run 2's own rewrite of ``F`` is then simply not a demanded output.
* A real chain is untouched: a run that read ``F@h1`` and wrote ``F@h2``
  (different bytes) is the producer of ``F@h2`` and keeps its parent.
* Applies to the level-1 and level-2 slice (``clew slice``, ``chain/dag
  --minimal``, claim verification, which verifies the minimal slice). The
  level-0 run closure, the full ``verify_chain`` / ``verify_dag`` lineage and
  the DAG renderers without ``--minimal`` are NOT changed: the read-back is a
  real recorded save->load handshake, and full-chain staleness still
  propagates through it.
"""

from __future__ import annotations

from .._hash import hashes_match

__all__ = ["originating_producer"]


def originating_producer(index, sid: str, path: str) -> str:
    """The run a slice credits with ``path``'s bytes as ``sid`` recorded them.

    Parameters
    ----------
    index : _RunIndex
        The slice's lazy run index (``inputs``, ``outputs``, ``parent_of``).
    sid : str
        A run that recorded ``path`` as an output.
    path : str
        The demanded output path.

    Returns
    -------
    str
        ``sid`` itself, unless ``sid`` read ``path`` at the hash it then wrote
        (a read-back rewrite) and that read binds to a recorded producer — then
        that producer, followed back while it is itself a read-back rewrite.
    """
    seen = {sid}
    while True:
        out = index.outputs(sid).get(path)
        inputs = index.inputs(sid)
        if out is None or path not in inputs:
            return sid
        if not hashes_match(inputs[path], out.get("hash")):
            return sid
        parent = index.parent_of(sid, path)
        if parent is None or parent in seen:
            return sid
        seen.add(parent)
        sid = parent


# EOF
