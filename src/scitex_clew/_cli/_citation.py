#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation CLI — `clew verify-citations` (compiler pre-flight) + `clew citation`.

``verify-citations`` is the check the compiler (scitex-writer) calls at compile
time: it takes a merged ``.bib`` and/or an explicit list of USED ``\\cite``
keys, and emits the per-key status map the writer gate branches on. Exit code is
the aggregate fail-loud contract (0 iff every key is ``verified``), so a
research-project compile can gate on ``$?`` directly.
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Dict, List, Optional

import click


def _json_mode(ctx: click.Context) -> bool:
    if ctx.obj and ctx.obj.get("json"):
        return True
    parent = ctx.parent
    while parent is not None:
        if parent.obj and parent.obj.get("json"):
            return True
        parent = parent.parent
    return False


# --- Minimal dependency-free .bib reader ------------------------------------
# We only need per-entry key + a few fields (doi/journal/note/title/author/
# year) to feed the gate. A full BibTeX parser is out of scope (and would add a
# dependency); this extracts entries robustly enough for the citation check.
_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s}]+)\s*,", re.IGNORECASE)
_WANTED_FIELDS = ("doi", "journal", "note", "title", "author", "year")


def _parse_bib(text: str) -> Dict[str, Dict[str, str]]:
    """Extract ``{cite_key: {field: value}}`` from BibTeX source (best-effort)."""
    entries: Dict[str, Dict[str, str]] = {}
    for match in _ENTRY_RE.finditer(text):
        key = match.group(1)
        # Slice from just after this entry header to the next '@' (or EOF).
        start = match.end()
        next_at = text.find("@", start)
        body = text[start:] if next_at == -1 else text[start:next_at]
        fields: Dict[str, str] = {}
        for field in _WANTED_FIELDS:
            fm = re.search(
                rf"\b{field}\s*=\s*[{{\"]([^}}\"]*)[}}\"]",
                body,
                re.IGNORECASE | re.DOTALL,
            )
            if fm:
                fields[field] = fm.group(1).strip()
        entries[key] = fields
    return entries


def _build_entries(
    bib: Optional[str], keys: Optional[str]
) -> List[Dict[str, str]]:
    """Combine --bib metadata with the --keys filter into gate entries."""
    bib_entries: Dict[str, Dict[str, str]] = {}
    if bib:
        bib_path = Path(bib)
        if not bib_path.exists():
            raise click.ClickException(f"--bib file not found: {bib}")
        bib_entries = _parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))

    if keys:
        wanted = [k.strip() for k in keys.split(",") if k.strip()]
        return [{"key": k, **bib_entries.get(k, {})} for k in wanted]

    if bib_entries:
        return [{"key": k, **fields} for k, fields in bib_entries.items()]

    raise click.ClickException("provide --bib and/or --keys")


@click.command(
    "verify-citations",
    epilog=(
        "Example:\n"
        "  $ scitex-clew verify-citations --bib merged.bib --json\n"
        "  $ scitex-clew verify-citations --bib merged.bib --keys Berens2009,Foo2020"
    ),
)
@click.option("--bib", "bib", default=None, help="Path to a merged .bib file.")
@click.option(
    "--keys",
    "keys",
    default=None,
    help="Comma-separated USED \\cite keys (default: every key in --bib).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (json emits the per-key status map).",
)
@click.pass_context
def verify_citations_cmd(
    ctx: click.Context, bib: Optional[str], keys: Optional[str], fmt: str
) -> None:
    """Verify manuscript \\cite keys against the clew citation ledger.

    Exit 0 iff every key is ``verified``; otherwise the aggregate fail-loud
    exit code (CITATION_STUB=14 / CITATION_UNRESOLVED=15 / CITATION_UNLINKED=16,
    or HASH_MISMATCH on drift). The compiler gates the build on this code.
    """
    from scitex_clew._citation import verify_all_citations, verify_citations
    from scitex_clew._citation._api import format_verify_map

    entries = _build_entries(bib, keys)
    per_key = verify_citations(entries)
    result = verify_all_citations(entries)

    as_json = fmt == "json" or _json_mode(ctx)
    if as_json:
        click.echo(
            _json.dumps(
                {
                    "exit_code": result.exit_code,
                    "exit_name": result.exit_name,
                    "ok": result.ok,
                    "reason": result.reason,
                    "counts": result.counts,
                    "citations": per_key,
                },
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(format_verify_map(per_key))
        click.echo(f"\n{result.exit_name}: {result.reason}")

    ctx.exit(result.exit_code)


@click.group("citation")
def citation() -> None:
    """Citation-node operations (list / verify \\cite -> scholar source)."""


@citation.command(
    "list",
    epilog=(
        "Example:\n"
        "  $ scitex-clew citation list\n"
        "  $ scitex-clew citation list --status stub --json"
    ),
)
@click.option(
    "--manuscript", "manuscript", default=None, help="Filter by manuscript file."
)
@click.option("--status", "status", default=None, help="Filter by status.")
@click.option("--limit", type=int, default=1000, help="Maximum nodes to list.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON (also accepted at top level).",
)
@click.pass_context
def citation_list(
    ctx: click.Context, manuscript, status, limit: int, as_json: bool
) -> None:
    """List registered citation nodes."""
    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True
    from scitex_clew._citation import format_citations, list_citations

    cits = list_citations(manuscript_file=manuscript, status=status, limit=limit)
    if _json_mode(ctx):
        click.echo(
            _json.dumps(
                {"count": len(cits), "citations": [c.to_dict() for c in cits]},
                indent=2,
                default=str,
            )
        )
    else:
        click.echo(format_citations(cits))


# EOF
