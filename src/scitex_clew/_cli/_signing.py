#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI for the manifest trust layer: keygen / sign / verify-signatures.

``clew keygen`` mints an Ed25519 keypair (private OFF-tree, public committed as
``signing.pub``); ``clew sign`` signs a source/exception manifest with the
private key; ``clew verify-signatures`` checks a manifest against the committed
public key. Signing means "without the key it can't be run/edited": any edit
breaks the signature and re-signing needs the private key the human holds.

Requires the ``[all]`` extra (python-cryptography); the verbs fail-loud with an
install hint if it is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from .._db._core import _find_project_root


def _default_key_path() -> Path:
    env = os.environ.get("SCITEX_CLEW_SIGNING_KEY")
    if env:
        return Path(env)
    return Path.home() / ".scitex" / "clew" / "signing.key"


def _default_pub_path() -> Path:
    return _find_project_root() / ".scitex" / "clew" / "signed" / "signing.pub"


def _resolve_manifest(manifest) -> Path:
    if manifest:
        return Path(manifest)
    from .._sources import resolve_sources_path

    return Path(resolve_sources_path()[0])


@click.command(
    "keygen",
    epilog=(
        "Example:\n"
        "  $ scitex-clew keygen\n"
        "  $ scitex-clew keygen --key ~/.keys/clew-signing.key"
    ),
)
@click.option("--key", type=click.Path(), help="Private key output path (default ~/.scitex/clew/signing.key).")
@click.option("--pub", type=click.Path(), help="Public key output path (default <root>/.scitex/clew/signed/signing.pub).")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing private key. DANGER: invalidates every prior signature.",
)
def keygen_cmd(key, pub, force):
    """Generate an Ed25519 signing keypair.

    Writes the PRIVATE key (0600) to --key/$SCITEX_CLEW_SIGNING_KEY/~/.scitex/clew/
    signing.key — keep it OFF the repo tree and BACK IT UP — and the PUBLIC key to
    signed/signing.pub — COMMIT that so the gate can verify.
    """
    from .._sources._signing import generate_keypair

    key_path = Path(key) if key else _default_key_path()
    pub_path = Path(pub) if pub else _default_pub_path()

    if key_path.exists() and not force:
        raise click.ClickException(
            f"private key already exists at {key_path}. Refusing to overwrite "
            "(that would invalidate every manifest signed with the old key). "
            "Use --force only if you intend to rotate + re-sign everything."
        )

    private_pem, public_pem = generate_keypair()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(private_pem)
    os.chmod(key_path, 0o600)
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_bytes(public_pem)

    click.echo(f"[OK] private key -> {key_path} (mode 0600 — keep OFF-TREE + BACK UP)")
    click.echo(f"[OK] public key  -> {pub_path} (COMMIT this; the gate verifies against it)")
    click.echo("Next: `clew sign` your sources.json, then commit signing.pub.")


@click.command(
    "sign",
    epilog=(
        "Example:\n"
        "  $ scitex-clew sign\n"
        "  $ scitex-clew sign .scitex/clew/sources.json"
    ),
)
@click.argument("manifest", required=False, type=click.Path())
@click.option("--key", type=click.Path(exists=True), help="Private key (default ~/.scitex/clew/signing.key or $SCITEX_CLEW_SIGNING_KEY).")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
def sign_cmd(manifest, key, as_json):
    """Sign a source/exception MANIFEST with the private key.

    MANIFEST defaults to the resolved sources manifest. Signs the canonical form
    (pretty-JSON minus the signature, sort_keys) and writes the manifest back in
    that same canonical serialization with the signature attached.
    """
    from .._sources._signing import sign_manifest

    key_path = Path(key) if key else _default_key_path()
    if not key_path.exists():
        raise click.ClickException(
            f"no private key at {key_path}. Run `clew keygen` first "
            "(or pass --key / set $SCITEX_CLEW_SIGNING_KEY)."
        )
    mpath = _resolve_manifest(manifest)
    if not mpath.exists():
        raise click.ClickException(f"manifest not found: {mpath}")

    raw = json.loads(mpath.read_text())
    raw["signature"] = sign_manifest(raw, key_path.read_bytes())
    # Write back in the canonical serialization so the on-disk pretty-JSON
    # (minus its signature) IS the signed byte string.
    mpath.write_text(
        json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False)
    )

    if as_json:
        click.echo(json.dumps({"signed": str(mpath), "algo": "ed25519"}, indent=2))
        return
    click.echo(f"[OK] signed {mpath} (ed25519). Commit it alongside signing.pub.")


@click.command(
    "verify-signatures",
    epilog=(
        "Example:\n"
        "  $ scitex-clew verify-signatures\n"
        "  $ scitex-clew verify-signatures --json"
    ),
)
@click.argument("manifest", required=False, type=click.Path())
@click.option("--pub", type=click.Path(exists=True), help="Public key (default <root>/.scitex/clew/signed/signing.pub).")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def verify_signatures_cmd(ctx, manifest, pub, as_json):
    """Verify a MANIFEST's signature against the committed public key (fail-loud).

    Exit 0 iff the signature is present AND verifies; nonzero otherwise (unsigned
    or tampered). MANIFEST defaults to the resolved sources manifest.
    """
    from .._sources._signing import is_signed, verify_manifest

    mpath = _resolve_manifest(manifest)
    pub_path = Path(pub) if pub else _default_pub_path()
    if not mpath.exists():
        raise click.ClickException(f"manifest not found: {mpath}")
    if not pub_path.exists():
        raise click.ClickException(
            f"no public key at {pub_path} (commit signing.pub, or pass --pub)."
        )

    raw = json.loads(mpath.read_text())
    signed = is_signed(raw)
    valid = signed and verify_manifest(raw, pub_path.read_bytes())

    if as_json:
        click.echo(
            json.dumps(
                {"manifest": str(mpath), "signed": signed, "valid": valid}, indent=2
            )
        )
    elif valid:
        click.echo(f"[OK] signature valid: {mpath}")
    elif not signed:
        click.echo(f"[FAIL] unsigned manifest: {mpath}")
    else:
        click.echo(f"[FAIL] signature INVALID (tampered or wrong key): {mpath}")

    if not valid:
        ctx.exit(1)
