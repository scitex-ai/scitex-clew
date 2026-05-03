#!/usr/bin/env python3
"""Register an in-session intermediate value as a Clew claim.

Wrapper around `_claim.add_claim` for the agentic-reasoning use case
(see `_skills/scitex-clew/20_agentic-reasoning.md`). Lets an AI agent or
script register a computed intermediate value without needing to construct
a manuscript file path or line number — uses the active session's log file
as the synthetic source.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Optional

from ._claim import Claim, add_claim


def register_intermediate(
    name: str,
    value: Any,
    supports: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    claim_type: str = "value",
) -> Claim:
    """Register a computed intermediate as a Clew claim.

    Use this from inside a `@stx.session` script (or from an agent loop) to
    record any non-trivial intermediate value with explicit upstream support.
    The claim becomes part of the DAG and can be queried via `clew.chain`,
    `clew.dag`, or the MCP `clew_chain` / `clew_dag` tools.

    Parameters
    ----------
    name
        Descriptive identifier (e.g. `"acute_n_sig_pathways"`). Avoid generic
        names like `"result_3"` — the id is the only handle a future inspector
        has on the value.
    value
        The computed result. Coerced to string for storage; the hash chain
        sees `repr(value)` so types matter.
    supports
        List of upstream claim ids or session ids that this value depends on.
        Stored as JSON in the claim's value field for retrieval. None means
        no explicit upstream (use sparingly).
    session_id
        The session this value belongs to. If None, read from the
        `SCITEX_SESSION_ID` env var that `@stx.session` sets at start.
    claim_type
        One of `statistic`, `figure`, `table`, `text`, `value`. Defaults to
        `value` since intermediates are usually scalar / categorical results.

    Returns
    -------
    Claim
        The registered claim object.

    Raises
    ------
    ValueError
        If no session_id can be determined (env var unset and not passed).

    Examples
    --------
    Inside a `@stx.session` script:

    >>> from scitex_clew import register_intermediate
    >>> n_sig = sum(1 for p in pathways if p.padj < 0.05)
    >>> register_intermediate(
    ...     name="chronic_r2_n_sig_pathways",
    ...     value=n_sig,
    ...     supports=["chronic_r2_min_pvals", "reactome_pathways_v2024"],
    ... )
    """
    if session_id is None:
        session_id = os.environ.get("SCITEX_SESSION_ID")
    if not session_id:
        raise ValueError(
            "register_intermediate: no session_id given and SCITEX_SESSION_ID "
            "is not set in the environment. Either pass session_id explicitly "
            "or run inside a @stx.session-decorated script."
        )

    payload = {
        "name": name,
        "value": repr(value),
        "supports": list(supports) if supports else [],
    }

    script_path = sys.argv[0] if sys.argv else "<agent>"
    return add_claim(
        file_path=script_path,
        claim_type=claim_type,
        line_number=None,
        claim_value=json.dumps(payload, sort_keys=True),
        source_file=None,
        source_session=session_id,
    )
