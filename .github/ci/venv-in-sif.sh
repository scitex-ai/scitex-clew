#!/usr/bin/env bash
# The approved image provides UV; create a complete job-owned interpreter environment.
V="${1:?python version required}"
BASE_PY="/opt/venv-$V/bin/python"
test -x "$BASE_PY"
UV="$(command -v uv)"
test -x "$UV"
"$UV" venv --python "$BASE_PY" "$CLEW_CI_STATE/venv"
PY="$CLEW_CI_STATE/venv/bin/python"
export PATH="$CLEW_CI_STATE/venv/bin:/usr/local/bin:/usr/bin:/bin"
