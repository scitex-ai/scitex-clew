"""Validate source, artifacts and installed leaf resource without importing Clew."""
import argparse
from email.parser import Parser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--source", action="store_true")
parser.add_argument("--dist", type=Path)
parser.add_argument("--installed", type=Path)
args = parser.parse_args()
root = Path.cwd().resolve()
project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
version = project["version"]
expected = (root / ".scitex/dev/cli-audit-dict.yaml").read_bytes()
resource = root / "src/scitex_clew/_cli_audit_dict.yaml"
assert resource.read_bytes() == expected
if args.source:
    tags = subprocess.check_output(["git", "tag", "--points-at", "HEAD"], text=True).splitlines()
    assert "v" + version in tags, "Checked-out commit must own the package version tag"
report = {"name": project["name"], "version": version,
          "resource_sha256": hashlib.sha256(expected).hexdigest()}
if args.dist:
    wheels = list(args.dist.glob("*.whl")); sdists = list(args.dist.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        metadata = Parser().parsestr(wheel.read(next(name for name in wheel.namelist() if name.endswith(".dist-info/METADATA"))).decode())
        assert metadata["Name"] == project["name"] and metadata["Version"] == version
        assert wheel.read("scitex_clew/_cli_audit_dict.yaml") == expected
    with tarfile.open(sdists[0]) as sdist:
        metadata = Parser().parsestr(sdist.extractfile(next(member for member in sdist.getmembers() if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1)).read().decode())
        assert metadata["Name"] == project["name"] and metadata["Version"] == version
        for suffix in ["/.scitex/dev/cli-audit-dict.yaml", "/src/scitex_clew/_cli_audit_dict.yaml"]:
            matches = [member for member in sdist.getmembers() if member.name.endswith(suffix)]
            assert len(matches) == 1 and sdist.extractfile(matches[0]).read() == expected
    report["artifact_sha256"] = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in [wheels[0],sdists[0]]}
if args.installed:
    owners = [dist for dist in importlib.metadata.distributions(path=[str(args.installed)]) if dist.metadata["Name"] == project["name"]]
    assert len(owners) == 1
    owner = owners[0]; assert owner.version == version
    entries = [item for item in owner.files if str(item) == "scitex_clew/_cli_audit_dict.yaml"]
    assert len(entries) == 1
    path = owner.locate_file(entries[0]); resolved = path.resolve()
    assert resolved.is_relative_to(args.installed.resolve()) and not path.is_symlink()
    assert resolved.read_bytes() == expected
    assert "scitex_clew" not in sys.modules
    report["installed_resource_sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
print(json.dumps(report, sort_keys=True))
