#!/usr/bin/env bash
# Source inside the verified SIF. Only the outer wrapper chooses job state.
set -euo pipefail
: "${CLEW_CI_STATE:?job-owned state must be supplied by exec-in-sif.sh}"
[[ "$CLEW_CI_STATE" = /* ]] || { echo '::error::job state must be absolute'; exit 1; }
umask 077
mkdir -p "$CLEW_CI_STATE"/{scitex,config,data,cache,tmp,site,installed}
mkdir -p "$CLEW_CI_STATE/home"
export HOME="$CLEW_CI_STATE/home"
export TMPDIR="$CLEW_CI_STATE/tmp" SCITEX_DIR="$CLEW_CI_STATE/scitex"
export XDG_CONFIG_HOME="$CLEW_CI_STATE/config" XDG_DATA_HOME="$CLEW_CI_STATE/data"
export XDG_CACHE_HOME="$CLEW_CI_STATE/cache" XDG_STATE_HOME="$CLEW_CI_STATE"
export PIP_CACHE_DIR="$CLEW_CI_STATE/cache/pip" UV_CACHE_DIR="$CLEW_CI_STATE/cache/uv"
export PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
export NETRC="$CLEW_CI_STATE/netrc" PGPASSFILE="$CLEW_CI_STATE/pgpass"
: > "$NETRC"; : > "$PGPASSFILE"
export SCITEX_STORE_DSN=postgresql://127.0.0.1:1/clew_ci_unreachable
export SCITEX_CARDS_NOTIFY_DSN=postgresql://127.0.0.1:1/clew_ci_unreachable
unset VIRTUAL_ENV PGUSER PGHOST PGPORT PGSERVICE PGPASSWORD
