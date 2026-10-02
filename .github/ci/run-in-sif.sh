#!/usr/bin/env bash
# Legacy SIF test entry point; requires an explicit disposable PostgreSQL DSN.
set -euo pipefail
source .github/ci/job-state.sh
V="${1:?python version required}"
source .github/ci/venv-in-sif.sh "$V"
: "${SCITEX_CLEW_TEST_DSN:?explicit disposable test cluster required}"
export RUN_E2E=1 MPLBACKEND=Agg MPLCONFIGDIR="$CLEW_CI_STATE/mpl"
mkdir -p "$MPLCONFIGDIR"
"$UV" pip install --python "$PY" ".[all,dev]" pytest-xdist
"$UV" pip check --python "$PY"
"$PY" -c "import matplotlib; from matplotlib import font_manager; font_manager.fontManager"
umask 022
# Match the required native service jobs: each test owns real database connections.
# Host CPU count does not establish the disposable database's connection capacity.
exec nice -n 19 ionice -c 3 "$PY" -m pytest tests/ -q \
  --cov=scitex_clew --cov-report="xml:$CLEW_CI_STATE/coverage.xml" \
  --cov-report=term -p no:cacheprovider
