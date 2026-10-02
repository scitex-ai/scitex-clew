"""Structured CLI help using the public Dev CliHelp protocol.

Command callbacks, options and examples retain their original contracts.
"""

from scitex_dev.ecosystem import CliHelp, Example

CLI_HELP = {
    'verify_citations_cmd': CliHelp(
        summary='Verify manuscript \\cite keys against the clew citation ledger.',
        description=(
            'Exit 0 iff every key is ``verified``; otherwise the aggregate fail-loud\nexit code (CITATION_STUB=14 / CITATION_UNRESOLVED=15 / CITATION_UNLINKED=16,\nor HASH_MISMATCH on drift). The compiler gates the build on this code.',
        ),
        examples=(
            Example('{prog} verify-citations --bib merged.bib --json', ''),
            Example('{prog} verify-citations --bib merged.bib --keys Berens2009,Foo2020', ''),
        ),
    ),
    'citation': CliHelp(
        summary='Citation-node operations (list / verify \\cite -> scholar source).',
        examples=(
            Example('{prog} citation list', ''),
        ),
    ),
    'citation_list': CliHelp(
        summary='List registered citation nodes.',
        examples=(
            Example('{prog} citation list', ''),
            Example('{prog} citation list --status stub --json', ''),
        ),
    ),
    'claim': CliHelp(
        summary='Manuscript-claim operations (add / list / verify / remove / supersede).',
        examples=(
            Example('{prog} claim list', ''),
        ),
    ),
    'claim_add': CliHelp(
        summary='Register a claim linking a manuscript assertion to the verification chain.',
        examples=(
            Example("{prog} claim add --file-path paper.tex --type statistic --value 'p=0.003'", ''),
            Example('{prog} claim add --file-path paper.tex --type figure --line-number 42 --dry-run', ''),
        ),
    ),
    'claim_list': CliHelp(
        summary='List registered claims with optional filters.',
        examples=(
            Example('{prog} claim list', ''),
            Example('{prog} claim list --file-path paper.tex --type statistic --json', ''),
            Example('{prog} claim list --file-path-prefix /old/manuscripts/', ''),
        ),
    ),
    'claim_verify': CliHelp(
        summary="Verify a specific claim (by claim_id or 'file.tex:L42').",
        examples=(
            Example('{prog} claim verify <claim_id>', ''),
            Example('{prog} claim verify paper.tex:L42 --json', ''),
        ),
    ),
    'claim_register_intermediate': CliHelp(
        summary='Register a computed intermediate value as a claim in the DAG.',
        examples=(
            Example('{prog} claim register-intermediate --name n_sig_pathways \\', ''),
        ),
    ),
    'claim_remove': CliHelp(
        summary='Hard-delete a claim (or bulk-delete by path prefix).',
        description=(
            "Provide either a positional CLAIM_ID_OR_LOCATION (a claim_id, a\nlocation string like 'paper.tex:L42', or a bare file path), OR\n``--file-path-prefix`` to remove all claims under a path root.\nThese are mutually exclusive.",
            'Without ``-y/--yes`` the command refuses to act (no interactive\nprompts).  Use ``--dry-run`` to preview without deleting.',
        ),
        examples=(
            Example('{prog} claim remove claim_abc123 -y', ''),
            Example('{prog} claim remove paper.tex:L42 -y', ''),
            Example('{prog} claim remove --file-path-prefix /old/papers/ -y', ''),
            Example('{prog} claim remove claim_abc123 --dry-run', ''),
        ),
    ),
    'claim_supersede': CliHelp(
        summary='Soft-retire a claim (keeps audit trail; excluded from verify gate).',
        description=(
            'Superseded claims are excluded from ``clew verify`` and the default\n``clew claim list`` view but remain in the DB for audit purposes.',
            "Provide either a positional CLAIM_ID_OR_LOCATION (a claim_id, a\nlocation string like 'paper.tex:L42', or a bare file path), OR\n``--file-path-prefix`` to supersede all claims under a path root.\nThese are mutually exclusive.",
            'Bulk operations (``--file-path-prefix``) require ``-y/--yes``; no\ninteractive prompts are shown.',
        ),
        examples=(
            Example('{prog} claim supersede claim_abc123', ''),
            Example('{prog} claim supersede paper.tex:L42', ''),
            Example('{prog} claim supersede --file-path-prefix /old/papers/ -y', ''),
        ),
    ),
    'estimate': CliHelp(
        summary='Pre-flight runtime/success estimate for a script or target file.',
        description=(
            'SCRIPT_OR_TARGET can be:',
            '\x08\n  - a Python script path  (estimates that script directly)\n  - a target output file  (resolved to its producing script via the DB)',
            'Shows p50/p90 runtime, success rate, typical #outputs, and a heavy-job\nwarning when the estimated p90 runtime exceeds 5 minutes.',
            'Match tiers:',
            '\x08\n  exact_hash   — script unchanged since last run (most reliable)\n  path_history — script changed; using path-matched history (annotated)\n  unknown      — no prior runs; cannot estimate',
        ),
        examples=(
            Example('{prog} estimate scripts/train.py', ''),
            Example('{prog} estimate results/fig1.png', ''),
            Example('{prog} estimate scripts/train.py --json', ''),
        ),
    ),
    'export_claims': CliHelp(
        summary='Regenerate the claims.json artifact (per-claim, or --unified render feed).',
        examples=(
            Example('{prog} export-claims', ''),
            Example('{prog} export-claims --unified', ''),
            Example('{prog} export-claims --unified --path build/claims.json --json', ''),
        ),
    ),
    'export_hints': CliHelp(
        summary='Regenerate the manuscript-hints.json artifact (schema manuscript-hints/1).',
        examples=(
            Example('{prog} export-hints', ''),
            Example('{prog} export-hints --path build/hints.json --json', ''),
        ),
    ),
    'hash_file': CliHelp(
        summary='Print the full SHA-256 hex digest of a file.',
        examples=(
            Example('{prog} hash-file results/data.csv', ''),
            Example('{prog} hash-file results/data.csv --json', ''),
        ),
    ),
    'hash_directory': CliHelp(
        summary='Print SHA-256 of every file in a directory (one per line by default).',
        examples=(
            Example('{prog} hash-directory results/', ''),
            Example("{prog} hash-directory results/ --pattern '*.csv' --json", ''),
        ),
    ),
    'list_python_apis': CliHelp(
        summary='List Python APIs (scitex-clew public API tree).',
        description=(
            'Shows modules [M], classes [C], functions [F], and variables [V]\nwith signatures and optional docstrings.',
        ),
        examples=(
            Example('{prog} list-python-apis', ''),
            Example('{prog} list-python-apis -v', ''),
            Example('{prog} list-python-apis -vv', ''),
            Example('{prog} list-python-apis -vvv', ''),
            Example('{prog} list-python-apis --json', ''),
        ),
    ),
    'main': CliHelp(
        summary='clew - Hash-based reproducibility verification for scientific pipelines.',
        description=(
            '\x08\nConfiguration precedence (highest -> lowest):\n  1. Explicit command-line flags (e.g. --strict, --json)\n  2. --config PATH (an explicit config file, or a .scitex/clew scope dir)\n  3. Project scope: <git-root>/.scitex/clew/config.yaml\n  4. User scope:    ~/.scitex/clew/config.yaml  ($SCITEX_DIR relocates the root)\n  5. Built-in defaults\nWithin one scope, config.yaml is the base; config/*.yaml deep-merge on top.',
        ),
        examples=(
            Example('{prog} --help', ''),
            Example('{prog} --json hash-file results/data.csv', ''),
        ),
        version_of='scitex-clew',
    ),
    'mcp': CliHelp(
        summary='MCP (Model Context Protocol) server commands.',
        examples=(
            Example('{prog} mcp list-tools', ''),
        ),
    ),
    'list_tools': CliHelp(
        summary='List available MCP tools.',
        description=(
            '\x08\nVerbosity levels:\n  (none)  Tool names only\n  -v      Full signatures\n  -vv     Signatures + first line of description\n  -vvv    Signatures + full description',
        ),
        examples=(
            Example('{prog} mcp list-tools', ''),
            Example('{prog} mcp list-tools -vv', ''),
            Example('{prog} mcp list-tools --json', ''),
        ),
    ),
    'start_server': CliHelp(
        summary='Start the scitex-clew MCP server.',
        examples=(
            Example('{prog} mcp start', ''),
            Example('{prog} mcp start --dry-run', ''),
        ),
    ),
    'install': CliHelp(
        summary='Show installation instructions for MCP server integration.',
        examples=(
            Example('{prog} mcp install', ''),
            Example('{prog} mcp install --dry-run', ''),
        ),
    ),
    'doctor': CliHelp(
        summary='Check MCP server dependencies and configuration.',
        examples=(
            Example('{prog} mcp doctor', ''),
        ),
    ),
    'keygen_cmd': CliHelp(
        summary='Generate an Ed25519 signing keypair.',
        description=(
            'Writes the PRIVATE key (0600) to --key/$SCITEX_CLEW_SIGNING_KEY/~/.scitex/clew/\nsigning.key — keep it OFF the repo tree and BACK IT UP — and the PUBLIC key to\nsigned/signing.pub — COMMIT that so the gate can verify.',
        ),
        examples=(
            Example('{prog} keygen', ''),
            Example('{prog} keygen --key ~/.keys/clew-signing.key', ''),
        ),
    ),
    'sign_cmd': CliHelp(
        summary='Sign a source/exception MANIFEST with the private key.',
        description=(
            'MANIFEST defaults to the resolved sources manifest. Signs the canonical form\n(pretty-JSON minus the signature, sort_keys) and writes the manifest back in\nthat same canonical serialization with the signature attached.',
        ),
        examples=(
            Example('{prog} sign', ''),
            Example('{prog} sign .scitex/clew/sources.json', ''),
        ),
    ),
    'verify_signatures_cmd': CliHelp(
        summary="Verify a MANIFEST's signature against the committed public key (fail-loud).",
        description=(
            'Exit 0 iff the signature is present AND verifies; nonzero otherwise (unsigned\nor tampered). MANIFEST defaults to the resolved sources manifest.',
        ),
        examples=(
            Example('{prog} verify-signatures', ''),
            Example('{prog} verify-signatures --json', ''),
        ),
    ),
    'skills_group': CliHelp(
        summary='Agent-facing skills bundled with scitex-clew.',
        examples=(
            Example('{prog} skills list', ''),
            Example('{prog} skills get 01_installation', ''),
            Example('{prog} skills install', '→ ~/.scitex/dev/skills/scitex-clew/'),
            Example('{prog} skills install --claude-symlink', 'also expose to ~/.claude/skills/scitex/'),
        ),
    ),
    'skills_list': CliHelp(
        summary='List skill files bundled with this package.',
        examples=(
            Example('{prog} skills list', ''),
            Example('{prog} skills list --json', ''),
        ),
    ),
    'skills_get': CliHelp(
        summary='Print the contents of a skill file by NAME (e.g. `01_installation`).',
        examples=(
            Example('{prog} skills get 01_installation', ''),
            Example('{prog} skills get 02_quick-start --json', ''),
        ),
    ),
    'skills_install': CliHelp(
        summary="Install this package's skills into a target directory.",
        description=(
            '\x08\nDefault: symlink the entire `_skills/scitex-clew/` dir to\n~/.scitex/dev/skills/scitex-clew/ so add/rename/delete in\nsource propagates immediately.',
        ),
        examples=(
            Example('{prog} skills install', ''),
            Example('{prog} skills install --claude-symlink', ''),
            Example('{prog} skills install --no-link --dest /tmp/scitex-clew-skills', ''),
        ),
    ),
    'register_source_cmd': CliHelp(
        summary='Register FILE(s) as trusted sources (idempotent; hash-pinned).',
        description=(
            "Computes each file's sha256 and writes/updates a {path, sha256} entry in the\nmanifest (default: the resolved signed/sources.json). Re-registering a path\nupdates its hash. Paths may be given as arguments and/or via\n--from-list <file> (one path per line; # comments + blank lines skipped) —\nso a human-editable path list compiles straight into the signable JSON\nmanifest. The sanctioned human WRITE path — verify/export never write it.",
        ),
        examples=(
            Example('{prog} register-source data/raw.csv', ''),
            Example('{prog} register-source a.csv b.csv --json', ''),
        ),
    ),
    'list_sources_cmd': CliHelp(
        summary='List registered sources with a validity check (OK / TAMPERED / MISSING).',
        examples=(
            Example('{prog} list-sources', ''),
            Example('{prog} list-sources --json', ''),
        ),
    ),
    'unregister_source_cmd': CliHelp(
        summary='Remove FILE(s) from the registered-source manifest (idempotent).',
        examples=(
            Example('{prog} unregister-source data/raw.csv', ''),
        ),
    ),
    'grounding_cmd': CliHelp(
        summary='Per-claim grounding verdict for CLAIM_LOCATION (claim_id or file.tex:L42).',
        description=(
            "Thin CLI wrapper around ``scitex_clew.is_claim_grounded`` — richer than a\nbare pass/fail bit: reports WHY (``reason``), the matched registered\nsource (if any), and an actionable ``fix_hint``. This is the primitive a\nlive inline editor (e.g. scitex-writer's SSOT paper editor) polls per\nclaim.",
        ),
        examples=(
            Example('{prog} grounding claim_abc123', ''),
            Example('{prog} grounding paper.tex:L42 --workdir ./paper --json', ''),
        ),
    ),
    'stamp': CliHelp(
        summary='Record a temporal stamp (root hash + ISO-8601 timestamp).',
        examples=(
            Example('{prog} stamp', ''),
            Example('{prog} stamp --backend rfc3161 --service-url <tsa-url>', ''),
            Example('{prog} stamp --session-ids id1,id2 --json', ''),
        ),
    ),
    'list_stamps': CliHelp(
        summary='List recorded stamps.',
        examples=(
            Example('{prog} list-stamps', ''),
            Example('{prog} list-stamps --limit 100 --json', ''),
        ),
    ),
    'check_stamp': CliHelp(
        summary='Verify a stamp (or the latest if STAMP_ID is omitted).',
        examples=(
            Example('{prog} check-stamp', ''),
            Example('{prog} check-stamp <stamp_id> --json', ''),
        ),
    ),
    'gate_completeness_cmd': CliHelp(
        summary='Assert a strict 1:1 correspondence between a submission and grounded claims.',
        description=(
            "Loads --submission (a {question_id: claim_id} JSON) and checks it against\nclew's GROUNDED claim_ids. Exits 0 when the correspondence is exactly 1:1;\nexits 1 with the failure report on any missing / orphan / cardinality\nviolation.",
        ),
        examples=(
            Example('{prog} gate-completeness --submission answers.json', ''),
            Example('{prog} gate-completeness --submission answers.json --json', ''),
        ),
    ),
    'status': CliHelp(
        summary='Git-status-like overview of verification state.',
        examples=(
            Example('{prog} status', ''),
            Example('{prog} status --json', ''),
        ),
    ),
    'list_runs': CliHelp(
        summary='List tracked runs.',
        examples=(
            Example('{prog} list-runs', ''),
            Example('{prog} list-runs --status success --limit 10 --json', ''),
        ),
    ),
    'verify': CliHelp(
        summary='Verify registered claims (no arg) or a specific run (SESSION_ID).',
        description=(
            "\x08\nFAIL-LOUD EXIT CODES (claim-set mode — the agent contract):\n  0   OK              every registered claim is source-verified\n  10  UNVERIFIED      claim(s) registered but never verified (fabrication)\n  11  SOURCE_MISSING  a claim's source file is gone\n  12  HASH_MISMATCH   a claim's source changed since registration\n  13  NO_LINEAGE      --strict: source has no @stx.session lineage\n  17  UNSOURCED       link-verified but ungrounded (no registered source);\n                      only when the source gate is active (a manifest exists)\n  20  NO_CLAIMS       no claims registered — nothing to verify",
            'A solver MUST run ``clew verify [--strict]`` before signalling DONE.\nDONE is legitimate ONLY on exit 0; any nonzero code means the agent\nmust abstain honestly (null + reason) instead of claiming success.',
        ),
        examples=(
            Example('{prog} verify', 'verify ALL registered claims'),
            Example('{prog} verify --strict', 'also require @stx.session lineage'),
            Example('{prog} verify <session_id>', 'verify one run, fail loud'),
            Example('{prog} verify --json', ''),
        ),
    ),
    'stats': CliHelp(
        summary='Database statistics.',
        examples=(
            Example('{prog} show-stats', ''),
            Example('{prog} show-stats --json', ''),
        ),
    ),
    'dag': CliHelp(
        summary='Verify the DAG for one or more targets (or every claim).',
        examples=(
            Example('{prog} dag --target results/foo.csv --json', ''),
            Example('{prog} dag --claims --strict --json', ''),
        ),
    ),
    'chain': CliHelp(
        summary='Verify the provenance chain that produced a target file.',
        description=(
            'Walks backwards through every upstream session that contributed to\nTARGET_FILE and re-hashes each one.',
        ),
        examples=(
            Example('{prog} chain results/fig1.png', ''),
            Example('{prog} chain results/fig1.png --json', ''),
        ),
    ),
    'rerun_dag': CliHelp(
        summary='Re-execute the DAG in a sandbox and compare outputs (slow, thorough).',
        description=(
            'Originals are never overwritten.',
        ),
        examples=(
            Example('{prog} rerun-dag', ''),
            Example('{prog} rerun-dag --target results/fig1.png --timeout 600 --json', ''),
        ),
    ),
    'rerun_claims': CliHelp(
        summary='Re-execute every claim-backing session in a sandbox and compare.',
        examples=(
            Example('{prog} rerun-claims', ''),
            Example('{prog} rerun-claims --type statistic --json', ''),
        ),
    ),
    'mermaid': CliHelp(
        summary='Generate Mermaid DAG diagram or static image.',
        description=(
            "\x08\nDAG-slicing options scope large provenance graphs to manageable slices:\n  --target FILE      restrict to FILE's upstream cone\n  --grouper NAME     collapse related nodes (directory/pattern/etc.)\n  --no-files         session-to-session edges only (fewest nodes)\n  --max-depth N      limit traversal depth",
            'When --format mermaid (default), output is identical to the historical\ntext-only behaviour.  When --format png|svg, a static image is written\nvia matplotlib (no mmdc / headless Chrome required).',
            'When --claims is combined with slicing options, the claims-based DAG is\nbuilt first and then the slicing options are applied.\nNote: --target is only honoured in multi-target / direct mode;\nin claims-only mode the full claims DAG is built.',
        ),
        examples=(
            Example('{prog} print-mermaid > dag.mmd', ''),
            Example('{prog} print-mermaid --claims --json', ''),
            Example('{prog} print-mermaid --target results/foo.csv', ''),
            Example('{prog} print-mermaid --grouper directory --no-files', ''),
            Example('{prog} print-mermaid --max-depth 3', ''),
            Example('{prog} print-mermaid --format png --output dag.png', ''),
            Example('{prog} print-mermaid --format svg', ''),
        ),
    ),
}
