# Clew GUI plugin workflow

Read the SDK GUI ownership skill first. Clew owns `src/scitex_clew/_django`;
Hub supplies generic identity, project/storage/store capabilities and chrome.
Do not add Clew schemas, operations or UI behavior to Hub.

Use the GUI extra and the `scitex.apps` AppConfig entry point. Preserve
`clew_app` label, registry table names and initial migration when moving
existing deployments. Do not perform an unreviewed registry data migration.
The manifest names its installed distribution, not a manually copied version.

Templates extend the shared app shell. API clients use the declared mount
marker and the project displayed in their tab. Root is explicitly empty;
missing metadata must fail instead of guessing a Hub URL. Leaf-built JS
chunks must be present in the installed wheel, independently of Hub's Vite.

Private provenance requires the host's request-bound project and store
capabilities. Credentials are private configuration, not request parameters.
Check the PostgreSQL login/tenant/schema/policies before reading; avoid any
ambient/default store fallback. Run one isolated adapter process per request
for Clew's cached DB/environment/cwd. This is not an OS filesystem sandbox.
Keep Sources and researcher-defined Claims unchanged while validating hashes.

Hosted private reads require authentication and project access; mutations
also require an explicit write capability and CSRF for browser sessions.
Public hash proofs disclose no user metadata. Registration badges must not
assert hash verification, rerun success or scientific validity.

For standalone validation, use a new loopback-only workspace and an explicit
private `SCITEX_CLEW_GUI_CONFIG` file. The local providers consume the same
capability contract. Missing configuration is unavailable; never interpret
it as empty research history. Do not use managed 55432/55433 for synthetic
tests or query another user's rows.

Check standalone and prefixed mounts, templates, wheel assets, desktop and
mobile interactions, project identity, cross-user/readonly/CSRF/path denial,
unavailable states and concurrency. Then separately validate the actual
Cloud PostgreSQL version/pool, filesystem sandbox and scientific workflow.
The canonical App/UI owner is `scitex-sdk` (`scitex_sdk.app` and
`scitex_sdk.ui`), with resource prefixes `scitex_sdk/app` and `scitex_sdk/ui`.
Keep persisted compatibility labels and the `scitex_app_content` block.
SDK 0.3.0 remains unpublished; install its reviewed wheel or checkout until
publication. Tenant `TenantScope`/`inspect_tenant_store` APIs are a separate
unpublished scitex-dev prerequisite. Published Dev 0.61.0 does not supply
them, so private provenance must remain unavailable (503) there. Shell and
project preview do not require tenant provisioning.
