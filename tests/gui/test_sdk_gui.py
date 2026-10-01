"""Exercise the real standalone Django shell and installed SDK resources."""

import json
import os
import subprocess
import sys


def test_standalone_shell_uses_sdk_resources_and_preserves_model_identity(tmp_path):
    project = tmp_path / "projects" / "alpha"
    project.mkdir(parents=True)
    (project / "notes.txt").write_text("Synthetic alpha preview", encoding="utf-8")
    config = tmp_path / "gui.json"
    config.write_text(
        json.dumps({"project_root": str(project.parent), "project_stores": {}}),
        encoding="utf-8",
    )
    config.chmod(0o600)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SCITEX_")
        and key not in {"DJANGO_SETTINGS_MODULE", "COVERAGE_PROCESS_START"}
    }
    environment.update(
        DJANGO_SETTINGS_MODULE="scitex_clew._django.settings",
        SCITEX_CLEW_GUI_CONFIG=str(config),
        SCITEX_DIR=str(tmp_path / "scitex-state"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    program = '''
import django
django.setup()
from html.parser import HTMLParser
from django.apps import apps
from django.contrib.staticfiles import finders
from django.db.migrations.loader import MigrationLoader
from django.test import Client

assert apps.get_app_config("scitex_app").name == "scitex_sdk.app"
assert apps.get_app_config("scitex_ui").name == "scitex_sdk.ui"
assert apps.get_app_config("clew_app").name == "scitex_clew._django"
assert apps.get_model("clew_app", "HashRegistration")._meta.db_table == "clew_app_hashregistration"
assert ("clew_app", "0001_initial") in MigrationLoader(None).disk_migrations
client = Client(HTTP_HOST="localhost")
page = client.get("/?project=alpha")
assert page.status_code == 200
assert b'data-project-ref="alpha"' in page.content
assert client.get("/api/file/?project=alpha&path=notes.txt").json()["content"] == "Synthetic alpha preview"

class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        url = attrs.get("src") or attrs.get("href", "")
        if url.startswith("/static/"):
            self.paths.append(url.removeprefix("/static/").split("?", 1)[0])
assets = Assets()
assets.feed(page.content.decode())
assert "scitex_sdk/ui/css/shell/app-shell.css" in assets.paths
assert "clew_app/js/clew-init.js" in assets.paths
assert "clew_app/clew-icon.svg" in assets.paths
for name in assets.paths:
    assert finders.find(name) is not None, name
'''
    completed = subprocess.run(
        [sys.executable, "-P", "-c", program],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
