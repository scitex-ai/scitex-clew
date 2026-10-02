#!/usr/bin/env bash
# Source inside the verified SIF. Only the outer wrapper chooses job state.
set -euo pipefail
: "${CLEW_CI_STATE:?job-owned state must be supplied by exec-in-sif.sh}"
[[ "$CLEW_CI_STATE" = /* ]] || { echo '::error::job state must be absolute'; exit 1; }
umask 077
mkdir -p "$CLEW_CI_STATE"/{scitex,config,data,cache,tmp,site,installed}
mkdir -p "$CLEW_CI_STATE/gnupg"
export TMPDIR="$CLEW_CI_STATE/tmp" SCITEX_DIR="$CLEW_CI_STATE/scitex"
export XDG_CONFIG_HOME="$CLEW_CI_STATE/config" XDG_DATA_HOME="$CLEW_CI_STATE/data"
export XDG_CACHE_HOME="$CLEW_CI_STATE/cache" XDG_STATE_HOME="$CLEW_CI_STATE"
export XDG_RUNTIME_DIR="$CLEW_CI_STATE/tmp" GNUPGHOME="$CLEW_CI_STATE/gnupg"
export PIP_CACHE_DIR="$CLEW_CI_STATE/cache/pip" UV_CACHE_DIR="$CLEW_CI_STATE/cache/uv"
export PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple
export UV_NO_CONFIG=1 PIP_NO_INPUT=1
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
export NETRC="$CLEW_CI_STATE/netrc" PGPASSFILE="$CLEW_CI_STATE/pgpass"
: > "$NETRC"; : > "$PGPASSFILE"
printf '{}\n' > "$CLEW_CI_STATE/config.yaml"
export SCITEX_CONFIG_PATH="$CLEW_CI_STATE/config.yaml"
export PGSERVICEFILE="$CLEW_CI_STATE/pgservice" PGSYSCONFDIR="$CLEW_CI_STATE"
: > "$PGSERVICEFILE"
export PGHOST="$CLEW_CI_STATE/refused-pg-socket" PGPORT=1 PGCONNECT_TIMEOUT=2 PGSSLMODE=disable
export PGSSLCERT="$PGPASSFILE" PGSSLKEY="$PGPASSFILE"
export NPM_CONFIG_USERCONFIG="$CLEW_CI_STATE/npm-user.conf"
export NPM_CONFIG_GLOBALCONFIG="$CLEW_CI_STATE/npm-global.conf"
export NPM_CONFIG_CACHE="$CLEW_CI_STATE/cache/npm"
: > "$NPM_CONFIG_USERCONFIG"; : > "$NPM_CONFIG_GLOBALCONFIG"
export SCITEX_STORE_DSN=postgresql://127.0.0.1:1/clew_ci_unreachable
export SCITEX_CARDS_NOTIFY_DSN=postgresql://127.0.0.1:1/clew_ci_unreachable
unset VIRTUAL_ENV PGUSER PGDATABASE PGSERVICE PGPASSWORD
