#!/usr/bin/env bash
# Publish only validated tag artifacts with ephemeral OIDC credentials.
set -euo pipefail
source .github/ci/job-state.sh
V="${1:-3.12}"
source .github/ci/venv-in-sif.sh "$V"
"$PY" .github/ci/check-dist.py --source --dist dist
(cd dist && sha256sum --check SHA256SUMS)
WHEELS=(dist/scitex_clew-*.whl)
[ "${#WHEELS[@]}" -eq 1 ]
WHEEL="${WHEELS[0]}"
"$UV" pip install --python "$PY" "$WHEEL[all,dev]" twine
"$UV" pip check --python "$PY"
"$PY" -m twine check dist/*.whl dist/*.tar.gz
INSTALLED_SITE="$("$PY" -c 'import sysconfig; import sys; sys.stdout.write(sysconfig.get_paths()["purelib"])')"
"$PY" .github/ci/check-dist.py --dist dist --installed "$INSTALLED_SITE"
"$PY" .github/ci/publish-oidc.py dist
