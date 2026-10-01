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
candidate needs unpublished SDK 0.3.0, App 0.26.2 and scitex-dev tenant APIs.
Full deployed middleware, PostgreSQL 18/PgBouncer, filesystem isolation,
shared-project access and the paper's scientific chain remain separate gates.
