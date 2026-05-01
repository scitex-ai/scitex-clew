#!/usr/bin/env python3
"""Skills introspection MCP tools (audit-mcp-tools §5).

Mirrors the canonical pattern in scitex-audio commit b47dbf2.
Self-contained — no scitex-dev runtime dependency, so resilient to
scitex-dev's in-flight 0.11.0 layout refactor.
"""

import json
from pathlib import Path

from fastmcp import FastMCP

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "_skills" / "scitex-clew"


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def clew_skills_list() -> str:
        """List the names of every skill page shipped by scitex-clew.

        Returns
        -------
            JSON string with `{"success": true, "package": "scitex-clew",
            "skills": ["01_quick-start", "02_grouping", ...]}`.
        """
        try:
            names = sorted(
                p.stem for p in _SKILLS_DIR.glob("*.md") if p.name != "SKILL.md"
            )
            return json.dumps(
                {"success": True, "package": "scitex-clew", "skills": names},
                indent=2,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    def clew_skills_get(name: str) -> str:
        """Fetch the full Markdown content of one scitex-clew skill page.

        Args:
            name: Skill page name without `.md`, e.g. `01_quick-start`.

        Returns
        -------
            JSON string with `{"success": true, "package": "scitex-clew",
            "name": <name>, "content": <markdown>}`, or an error envelope.
        """
        try:
            target = _SKILLS_DIR / f"{name}.md"
            if not target.exists():
                available = sorted(
                    p.stem for p in _SKILLS_DIR.glob("*.md") if p.name != "SKILL.md"
                )
                return json.dumps(
                    {
                        "success": False,
                        "error": f"unknown skill {name!r}; available: {available}",
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "success": True,
                    "package": "scitex-clew",
                    "name": name,
                    "content": target.read_text(encoding="utf-8"),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


# EOF
