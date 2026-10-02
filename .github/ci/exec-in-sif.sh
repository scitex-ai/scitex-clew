#!/usr/bin/env bash
# Outer wrapper: verify the approved SIF digest, isolate state and bind only the job.
set -euo pipefail
INNER="${1:?inner script required}"
shift
case "$INNER" in build-in-sif.sh|publish-in-sif.sh|run-in-sif.sh) ;; *) echo '::error::unknown inner script'; exit 1;; esac
APPTAINER="${SCITEX_CI_APPTAINER:?approved absolute Apptainer path required}"
SIF="${SCITEX_CI_SIF:?approved absolute SIF path required}"
EXPECTED="${SCITEX_CI_SIF_SHA256:?approved SIF SHA256 required}"
[[ "$APPTAINER" = /* && "$SIF" = /* && "$EXPECTED" =~ ^[a-fA-F0-9]{64}$ ]] || { echo '::error::absolute paths and a SHA256 are required'; exit 1; }
[[ "$EXPECTED" == "aa5836a6c317640d7e20f01eb79aa7385b3dca2f369b595065c50ba3dd34a7d5" ]] || { echo '::error::SIF digest is not the approved CI image'; exit 1; }
[ -x "$APPTAINER" ] && [ -f "$SIF" ]
printf '%s  %s\n' "$EXPECTED" "$SIF" | sha256sum --check --status
: "${RUNNER_TEMP:?job-owned runner temporary directory required}"
STATE="$(mktemp -d "$RUNNER_TEMP/clew-${GITHUB_JOB:?}-${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}.XXXXXX")"
mkdir -p "$STATE/apptainer-config" "$STATE/apptainer-tmp"
# execve receives the whitelist directly; ephemeral OIDC values stay out of argv.
exec /usr/bin/python3 -I -S - "$APPTAINER" "$SIF" "$STATE" "$INNER" "$@" <<'PY_EXEC'
import os
import sys
from pathlib import Path
apptainer, image, state, inner, *arguments = sys.argv[1:]
checkout = str(Path.cwd())
environment = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "APPTAINER_CONFIGDIR": state + "/apptainer-config",
    "APPTAINER_TMPDIR": state + "/apptainer-tmp",
    "APPTAINERENV_CLEW_CI_STATE": state,
    "APPTAINERENV_GITHUB_REF": os.environ["GITHUB_REF"],
}
if os.environ.get("SCITEX_CLEW_TEST_DSN"):
    environment["APPTAINERENV_SCITEX_CLEW_TEST_DSN"] = os.environ["SCITEX_CLEW_TEST_DSN"]
if inner == "publish-in-sif.sh":
    for name in ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL"):
        if not os.environ.get(name):
            raise SystemExit("Publish job requires its ephemeral OIDC context")
        environment["APPTAINERENV_" + name] = os.environ[name]
command = [apptainer, "exec", "--cleanenv", "--no-home", "--containall",
           "--pwd", checkout, "--bind", checkout + ":" + checkout,
           "--bind", state + ":" + state, image, "bash", ".github/ci/" + inner, *arguments]
os.execve(apptainer, command, environment)
PY_EXEC
