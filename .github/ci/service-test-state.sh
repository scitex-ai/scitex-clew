#!/usr/bin/env bash
# Source before native tests; service DSN is explicit, state is unique to this job.
set -euo pipefail
: "${SCITEX_CLEW_TEST_DSN:?explicit disposable service DSN required}"
: "${RUNNER_TEMP:?job-owned temporary directory required}"
CLEW_CI_STATE="$(mktemp -d "$RUNNER_TEMP/clew-tests.XXXXXX")"
export CLEW_CI_STATE
source .github/ci/job-state.sh
printf '{}\n' > "$CLEW_CI_STATE/config.yaml"
export SCITEX_CONFIG_PATH="$CLEW_CI_STATE/config.yaml"
export PGSERVICEFILE="$CLEW_CI_STATE/pgservice"
: > "$PGSERVICEFILE"
export PGHOST=127.0.0.1 PGPORT=1 PGCONNECT_TIMEOUT=2 PGSSLMODE=disable
export PGSSLCERT="$PGPASSFILE" PGSSLKEY="$PGPASSFILE"
export RUN_E2E=1 MPLBACKEND=Agg MPLCONFIGDIR="$CLEW_CI_STATE/matplotlib"
mkdir -p "$MPLCONFIGDIR"
# Native file permission assertions require the documented ordinary umask.
umask 022
