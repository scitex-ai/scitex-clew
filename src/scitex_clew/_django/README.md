# Clew GUI

The GUI is owned by `scitex_clew._django` and consumes `scitex-sdk` for the
shared shell and authorized host capabilities. Read the
[GUI workflow](../_skills/scitex-clew/40_gui-plugin.md) before changing it.

The same relative urlconf, templates and built assets run at the standalone
root and at a Hub/custom plugin mount. The `scitex.apps` entry point discovers
its AppConfig. The leaf manifest also supplies workspace content and agent
skill metadata. Label `clew_app`, table `clew_app_hashregistration` and the
initial migration remain unchanged from the former Hub app.

The private API provides runs, stats, claims, hash verification and DAG views.
It authenticates hosted requests, resolves an explicit authorized project,
checks all twenty current provenance tables for the expected tenant policies,
and isolates Clew state in a fresh process. Unavailable stores return 503;
no global-store or SQLite fallback is used. Requested/recorded file paths
must stay within the selected project. GET requests never rerun scripts.

Project previews and example scaffolding consume SDK read/write capabilities.
Preview reads open the SDK-normalized canonical path through directory
descriptors and refuse symlink components during the open. Legitimate aliases
such as `paper -> .scitex/writer` remain readable when their normalized target
is inside the authorized project. Only regular files are accepted. UTF-8 text
keeps its 4 MiB limit; image responses retain the existing streaming behavior
and formats. This reader requires POSIX descriptor-relative opens and Linux
no-follow flags; unsupported platforms return unavailable rather than falling
back to pathname reads. Provenance worker reads still need separate integration
with a rooted reader; the worker's containment checks are not an OS sandbox.
Session writes require CSRF. Public registry proofs remain anonymized; badges
claim registration only. A timestamp does not prove successful reproduction
or scientific correctness.

The standalone launcher binds loopback. `SCITEX_CLEW_GUI_CONFIG` may name a
private JSON file containing `project_root` and `project_stores`; each store
entry supplies `tenant_id`, `dsn`, `project_scope` and `owner_role`. Missing
stores are displayed as unavailable. This initial GUI requires explicitly
configured tenant stores and does not provision accounts or migrate archives.
The standalone providers support a single local user, not a shared server.

Build the assets from `frontend/package.json` and package every JS chunk.
Frontend tests cover root/custom mounts, project identity and safe rendering.
The Hub integration suite uses synthetic projects in disposable PostgreSQL,
including real browser checks for standalone and plugin modes. This local
candidate uses the physical `scitex_sdk.app` and `scitex_sdk.ui` packages in
the unpublished SDK 0.3.0 wheel. Its tenant APIs (`TenantScope` and
`inspect_tenant_store`) are a separate unpublished scitex-dev prerequisite;
published Dev 0.61.0 does not supply them. Shell and project preview work
without that prerequisite; private provenance APIs return unavailable (503).
Full deployed middleware, PostgreSQL 18/PgBouncer, filesystem isolation,
shared-project access and the paper's scientific chain remain separate gates.
