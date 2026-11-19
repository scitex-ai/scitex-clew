#!/usr/bin/env python3
"""`clew bundle {keygen,export,verify,rerun}` — the evidence exchange format.

See :mod:`scitex_clew._exchange`. ``verify`` and ``rerun`` are store-free:
they read only the bundle file and the checkout. ``rerun`` EXECUTES the
project's code — run it inside an isolated container.

Exit codes: ``0`` = ok; ``1`` = the bundle did not verify / reproduce (the
JSON output says why); ``2`` = usage error.
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path

import click
from scitex_dev.ecosystem import CliHelp, Example, SpecCommand, SpecGroup

_ROOT_OPTION = click.option(
    "--project-root",
    "project_root",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, exists=True),
    help="The project checkout (its root directory).",
)
_JSON_OPTION = click.option(
    "--json", "as_json", is_flag=True, help="Emit JSON (also accepted at top level)."
)
_YES_OPTION = click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for §2 audit-cli compliance (never prompts).",
)


def _json_mode(ctx: click.Context, as_json: bool) -> bool:
    while ctx is not None:
        if ctx.obj and ctx.obj.get("json"):
            return True
        ctx = ctx.parent
    return as_json


def _echo_json(payload) -> None:
    click.echo(_json.dumps(payload, indent=2, ensure_ascii=False, default=str))


@click.group(
    "bundle",
    cls=SpecGroup,
    help_spec=CliHelp(
        summary="Portable, signed evidence bundle: export, verify, rerun without a store.",
        examples=(
            Example("{prog} bundle export --sign-key ~/.scitex/clew/bundle.key"),
            Example("{prog} bundle verify .scitex/clew/evidence-bundle.json --json"),
            Example("{prog} bundle rerun .scitex/clew/evidence-bundle.json --json"),
        ),
    ),
)
def bundle() -> None:
    """Portable, signed evidence bundle (scitex-clew.evidence-bundle 1.0.0)."""


@bundle.command(
    "keygen",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Write a new Ed25519 private key file (mode 0600) for signing bundles.",
        examples=(Example("{prog} bundle keygen --out ~/.scitex/clew/bundle.key"),),
    ),
)
@click.option("--out", "out", required=True, type=click.Path(dir_okay=False),
              help="Private key path to create (never overwritten).")  # fmt: skip
@click.option("--dry-run", "dry_run", is_flag=True, help="Show what would be written.")
@_YES_OPTION
@_JSON_OPTION
@click.pass_context
def keygen(ctx, out: str, dry_run: bool, yes: bool, as_json: bool) -> None:
    """Generate an Ed25519 signing key; print its key_id and public key."""
    del yes
    import base64

    from .._exchange._signing import SigningUnavailable, generate_private_key_file

    path = Path(out).expanduser().resolve()
    if path.exists():
        raise click.ClickException(
            f"{path} already exists; refusing to overwrite a key (bundles "
            "signed with it would no longer be re-signable). Choose another --out."
        )
    if dry_run:
        payload = {"dry_run": True, "out": str(path), "alg": "ed25519"}
        _echo_json(payload) if _json_mode(ctx, as_json) else click.echo(
            f"DRY RUN — would write an Ed25519 private key (0600) to {path}"
        )
        return
    try:
        signer = generate_private_key_file(path)
    except SigningUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    payload = {
        "path": str(path),
        "alg": signer.alg,
        "key_id": signer.key_id,
        "public_key": base64.b64encode(signer.public_key).decode("ascii"),
    }
    if _json_mode(ctx, as_json):
        _echo_json(payload)
    else:
        click.echo(f"[KEY] {payload['alg']} key_id={payload['key_id']} -> {path}")
        click.echo(f"public_key={payload['public_key']}")
        click.echo("Keep the private key OFF the repository tree.")


@bundle.command(
    "export",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Build this project's evidence bundle from the store.",
        examples=(
            Example("{prog} bundle export"),
            Example("{prog} bundle export --sign-key ~/.scitex/clew/bundle.key --json"),
            Example("{prog} bundle export --out - --dry-run"),
        ),
    ),
)
@_ROOT_OPTION
@click.option("--out", "out", default=None,
              help="Bundle path (default <root>/.scitex/clew/evidence-bundle.json; '-' = stdout).")  # fmt: skip
@click.option("--sign-key", "sign_key", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Ed25519 private key file (from `clew bundle keygen`) to sign with.")  # fmt: skip
@click.option("--all-runs", "all_runs", is_flag=True,
              help="Export every recorded run, not only those that produced the files on disk.")  # fmt: skip
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Show what would be written; write nothing.",
)
@_YES_OPTION
@_JSON_OPTION
@click.pass_context
def export(ctx, project_root, out, sign_key, all_runs, dry_run, yes, as_json) -> None:
    """Export this project's runs and claims as a portable evidence bundle."""
    del yes
    from .._exchange import (
        BUNDLE_SCHEMA,
        BUNDLE_SCHEMA_VERSION,
        build_bundle,
        default_bundle_path,
        sign_document,
        write_bundle,
    )
    from .._exchange._signing import SigningUnavailable, load_signer

    json_mode = _json_mode(ctx, as_json)
    root = Path(project_root).resolve()
    target = None if out == "-" else Path(out or default_bundle_path(root)).resolve()
    if dry_run:
        payload = {"dry_run": True, "project_root": str(root),
                   "out": str(target) if target else "-", "signed": bool(sign_key),
                   "schema": BUNDLE_SCHEMA, "schema_version": BUNDLE_SCHEMA_VERSION}  # fmt: skip
        _echo_json(payload) if json_mode else click.echo(
            f"DRY RUN — would write {BUNDLE_SCHEMA} {BUNDLE_SCHEMA_VERSION} -> {payload['out']}"
        )
        return
    try:
        signer = load_signer(sign_key) if sign_key else None
    except SigningUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    document = build_bundle(root, all_runs=all_runs)
    if signer is not None:
        document = sign_document(document, signer)
    if target is None:
        click.echo(_json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False))
        return
    write_bundle(document, target)
    payload = {
        "path": str(target),
        "runs": len(document["runs"]),
        "claims": len(document["claims"]),
        "signed": "signature" in document,
        "key_id": (document.get("signature") or {}).get("key_id"),
    }
    if json_mode:
        _echo_json(payload)
    else:
        sig = f", signed by {payload['key_id']}" if payload["signed"] else ", unsigned"
        click.echo(
            f"[EXPORTED] {payload['runs']} run(s), {payload['claims']} claim(s){sig} -> {target}"
        )


@bundle.command(
    "verify",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Check a bundle's schema, signature and file hashes against a project tree.",
        examples=(
            Example("{prog} bundle verify .scitex/clew/evidence-bundle.json --json"),
            Example(
                "{prog} bundle verify bundle.json --project-root repo --expect-key-id 0123456789abcdef"
            ),
        ),
    ),
)
@click.argument("path", type=click.Path(dir_okay=False))
@_ROOT_OPTION
@click.option("--expect-key-id", "expect_key_id", default=None,
              help="Require a signature by this key id (16 hex).")  # fmt: skip
@click.option("--allow-missing", "allow_missing", is_flag=True,
              help="Report recorded files absent from the checkout as warnings, not failures.")  # fmt: skip
@_JSON_OPTION
@click.pass_context
def verify(ctx, path, project_root, expect_key_id, allow_missing, as_json) -> None:
    """Verify an evidence bundle (store-free); exit 0 iff it checks out."""
    from .._exchange import verify_bundle

    result = verify_bundle(path, project_root, expected_key_id=expect_key_id,
                           allow_missing=allow_missing)  # fmt: skip
    if _json_mode(ctx, as_json):
        _echo_json(result)
    else:
        files = result["files"]
        sig = result["signature"] or {}
        click.echo(f"[{'OK' if result['ok'] else 'FAIL'}] {path}")
        click.echo(f"  schema: {'valid' if result['schema_valid'] else 'INVALID'}")
        click.echo(f"  signature: {sig.get('reason', 'n/a')}")
        click.echo(f"  files: {files['matched']}/{files['checked']} match, "
                   f"{len(files['mismatched'])} differ, {len(files['missing'])} missing")  # fmt: skip
        for finding in result["findings"]:
            click.echo(f"  - {finding['code']}: {finding['message']}")
    sys.exit(0 if result["ok"] else 1)


@bundle.command(
    "rerun",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Re-execute a bundle's runs in a temp copy; compare outputs and claims.",
        description=(
            (
                "EXECUTES THE PROJECT'S CODE: run it only inside an isolated container. "
                "The project root is copied, never written; no store is reachable from the runs."
            ),
        ),
        examples=(
            Example("{prog} bundle rerun .scitex/clew/evidence-bundle.json --json"),
            Example(
                "{prog} bundle rerun bundle.json --project-root repo --timeout 1800 --out report.json"
            ),
            Example("{prog} bundle rerun bundle.json --dry-run"),
        ),
    ),
)
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@_ROOT_OPTION
@click.option("--timeout", "timeout", default=600.0, show_default=True, type=float,
              help="Seconds allowed per run.")  # fmt: skip
@click.option("--python", "python", default=None,
              help="Interpreter for the runs (default: the one running clew).")  # fmt: skip
@click.option("--out", "out", default=None, type=click.Path(dir_okay=False),
              help="Also write the rerun report to this file.")  # fmt: skip
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="List the runs that would be executed; execute nothing.",
)
@_YES_OPTION
@_JSON_OPTION
@click.pass_context
def rerun(ctx, path, project_root, timeout, python, out, dry_run, yes, as_json) -> None:
    """Re-run an evidence bundle's runs and recompute its claims; exit 0 iff all reproduce."""
    del yes
    from .._exchange import load_bundle, rerun_bundle
    from .._exchange._rerun import topological_runs

    json_mode = _json_mode(ctx, as_json)
    if dry_run:
        doc, _raw = load_bundle(path)
        runs = [r for r in doc.get("runs") or [] if isinstance(r, dict)]
        plan = [{"run_id": r["run_id"], "cwd": r.get("cwd"), "argv": r.get("argv")}
                for r in topological_runs(runs, doc.get("edges") or [])]  # fmt: skip
        payload = {
            "dry_run": True,
            "runs": plan,
            "claims": len(doc.get("claims") or []),
        }
        if json_mode:
            _echo_json(payload)
        else:
            for step in plan:
                click.echo(
                    f"DRY RUN — {step['run_id']}: (cd {step['cwd']}) python {' '.join(step['argv'] or [])}"
                )
        return
    report = rerun_bundle(path, project_root, timeout=timeout, python=python)
    if out:
        Path(out).write_text(
            _json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    ok = (
        report["executable"]
        and all(r["status"] == "reproduced" for r in report["runs"])
        and not any(c["status"] == "differs" for c in report["claims"])
    )
    if json_mode:
        _echo_json(report)
    else:
        click.echo(f"[{'REPRODUCED' if ok else 'NOT REPRODUCED'}] {path}")
        for run in report["runs"]:
            click.echo(f"  run {run['run_id']}: {run['status']}"
                       + (f" ({run['reason']})" if run.get("reason") else ""))  # fmt: skip
        for claim in report["claims"]:
            click.echo(f"  claim {claim['claim_id']}: {claim['status']}")
    sys.exit(0 if ok else 1)


# EOF
