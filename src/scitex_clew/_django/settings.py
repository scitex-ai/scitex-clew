"""Loopback-only standalone GUI; uses the same SDK capabilities as a plugin.

Optional SCITEX_CLEW_GUI_CONFIG names a private JSON file with project_root
and project_stores. Missing stores appear as unavailable, never empty success.
This GUI does not initialize or borrow an ambient shared PostgreSQL store.
"""

import json
import os
import secrets
from pathlib import Path

try:
    from django.core.exceptions import ImproperlyConfigured
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)

DEBUG = True
SECRET_KEY = secrets.token_urlsafe(48)
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
SCITEX_APP_MODE = "standalone"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "scitex_sdk.app",
    "scitex_sdk.ui",
    "scitex_clew._django.apps.ClewAppConfig",
]
MIDDLEWARE = ["django.middleware.csrf.CsrfViewMiddleware"]
ROOT_URLCONF = "scitex_clew._django.standalone_urls"
DATABASES = {}
STATIC_URL = "/static/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
            ]
        },
    }
]

config = {}
config_path = os.environ.get("SCITEX_CLEW_GUI_CONFIG")
if config_path:
    path = Path(config_path)
    try:
        if path.stat().st_mode & 0o077:
            raise ValueError("permissions")
        config = json.loads(path.read_text("utf-8"))
        if not isinstance(config, dict):
            raise TypeError("shape")
    except (OSError, ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "Clew GUI config must be a private valid JSON file"
        ) from exc

SCITEX_LOCAL_PROJECT_ROOT = config.get("project_root", str(Path.cwd().parent))
SCITEX_LOCAL_PROJECT_STORES = config.get("project_stores", {})
SCITEX_PROJECT_PROVIDER = "scitex_sdk.local.LocalProjectProvider"
SCITEX_PROJECT_STORAGE = "scitex_sdk.local.LocalProjectStorage"
SCITEX_PROJECT_STORE = "scitex_sdk.local.LocalProjectStore"
SCITEX_PROJECT_PROVIDER_URL = "project-list"
