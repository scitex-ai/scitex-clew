"""Native trusted publishing; tokens never appear in argv or diagnostic output."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
parsed = urllib.parse.urlsplit(url)
if parsed.scheme != "https":
    raise SystemExit("OIDC request URL must use HTTPS")
separator = "&" if parsed.query else "?"
try:
    request = urllib.request.Request(url + separator + "audience=pypi", headers={
        "Authorization": "bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(request, timeout=60) as response:
        jwt = json.load(response)["value"]
    request = urllib.request.Request("https://pypi.org/_/oidc/mint-token",
        data=json.dumps({"token": jwt}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        token = json.load(response)["token"]
    if not token:
        raise ValueError("empty token")
except Exception as error:
    raise SystemExit("OIDC trusted-publishing exchange failed: " + type(error).__name__) from None
artifacts = sorted(Path(sys.argv[1]).glob("*.whl")) + sorted(Path(sys.argv[1]).glob("*.tar.gz"))
if len(artifacts) != 2:
    raise SystemExit("Exactly one validated wheel and sdist are required")
environment = os.environ.copy()
environment.update(TWINE_USERNAME="__token__", TWINE_PASSWORD=token)
subprocess.run([sys.executable, "-m", "twine", "upload", "--non-interactive",
    "--disable-progress-bar", *map(str, artifacts)], env=environment, check=True)
