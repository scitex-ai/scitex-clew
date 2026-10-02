#!/usr/bin/env bash
# Native installer/application context; ambient provider identities stay outside it.
set -euo pipefail
: "${RUNNER_TEMP:?job-owned temporary directory required}"
service_tests=0
if [[ "${1-}" == --service-tests ]]; then
  service_tests=1
  shift
fi
[[ "$#" -gt 0 ]] || { echo '::error::native job command required'; exit 1; }
if [[ "$service_tests" == 1 ]]; then
  source .github/ci/service-test-state.sh
else
  if [[ -z "${CLEW_CI_STATE-}" ]]; then
    CLEW_CI_STATE="$(mktemp -d "$RUNNER_TEMP/clew-native.XXXXXX")"
    export CLEW_CI_STATE
    if [[ -n "${GITHUB_ENV-}" ]]; then
      printf 'CLEW_CI_STATE=%s\n' "$CLEW_CI_STATE" >> "$GITHUB_ENV"
    fi
  fi
  source .github/ci/job-state.sh
  umask 022
fi
export UV_PYTHON_INSTALL_DIR="$CLEW_CI_STATE/uv-python"
context=(
  "PATH=${PATH:?}" "LANG=C.UTF-8" "LC_ALL=C.UTF-8"
  "CLEW_CI_STATE=$CLEW_CI_STATE" "RUNNER_TEMP=$RUNNER_TEMP"
  "SCITEX_DIR=$SCITEX_DIR" "SCITEX_CONFIG_PATH=$SCITEX_CONFIG_PATH"
  "SCITEX_STORE_DSN=$SCITEX_STORE_DSN" "SCITEX_CARDS_NOTIFY_DSN=$SCITEX_CARDS_NOTIFY_DSN"
  "TMPDIR=$TMPDIR" "XDG_CONFIG_HOME=$XDG_CONFIG_HOME" "XDG_CACHE_HOME=$XDG_CACHE_HOME"
  "XDG_DATA_HOME=$XDG_DATA_HOME" "XDG_STATE_HOME=$XDG_STATE_HOME" "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
  "GNUPGHOME=$GNUPGHOME" "NETRC=$NETRC" "PGPASSFILE=$PGPASSFILE"
  "PGSERVICEFILE=$PGSERVICEFILE" "PGSYSCONFDIR=$PGSYSCONFDIR"
  "PGHOST=$PGHOST" "PGPORT=$PGPORT" "PGCONNECT_TIMEOUT=$PGCONNECT_TIMEOUT"
  "PGSSLMODE=$PGSSLMODE" "PGSSLCERT=$PGSSLCERT" "PGSSLKEY=$PGSSLKEY"
  "PIP_CONFIG_FILE=$PIP_CONFIG_FILE" "PIP_INDEX_URL=$PIP_INDEX_URL"
  "PIP_CACHE_DIR=$PIP_CACHE_DIR" "PIP_NO_INPUT=$PIP_NO_INPUT"
  "UV_CACHE_DIR=$UV_CACHE_DIR" "UV_NO_CONFIG=$UV_NO_CONFIG" "UV_PYTHON_INSTALL_DIR=$UV_PYTHON_INSTALL_DIR"
  "PYTHON_KEYRING_BACKEND=$PYTHON_KEYRING_BACKEND"
  "NPM_CONFIG_USERCONFIG=$NPM_CONFIG_USERCONFIG" "NPM_CONFIG_GLOBALCONFIG=$NPM_CONFIG_GLOBALCONFIG"
  "NPM_CONFIG_CACHE=$NPM_CONFIG_CACHE"
)
# Preserve the actual native HOME value; it never chooses job-owned state.
if [[ -v HOME ]]; then context+=("HOME=$HOME"); fi
if [[ "$service_tests" == 1 ]]; then
  context+=("SCITEX_CLEW_TEST_DSN=$SCITEX_CLEW_TEST_DSN" "RUN_E2E=$RUN_E2E"
            "MPLBACKEND=$MPLBACKEND" "MPLCONFIGDIR=$MPLCONFIGDIR")
fi
exec env -i "${context[@]}" "$@"
