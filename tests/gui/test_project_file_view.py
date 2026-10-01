"""Preview HTTP responses using real standalone capability providers."""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module", autouse=True)
def configured_django():
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            SECRET_KEY="synthetic-preview-tests",
            DEFAULT_CHARSET="utf-8",
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "scitex_sdk.app",
                "scitex_sdk.ui",
                "scitex_clew._django.apps.ClewAppConfig",
            ],
            SCITEX_APP_MODE="standalone",
        )
        django.setup()


@pytest.fixture
def preview(tmp_path):
    from django.test import RequestFactory, override_settings
    from scitex_clew._django.views.api import project_file

    root = tmp_path / "project"
    root.mkdir()
    factory = RequestFactory()

    def request(path, **parameters):
        req = factory.get("/api/file/", {"project": "project", "path": path, **parameters})
        req.user = SimpleNamespace(is_authenticated=False)
        req.session = {}
        with override_settings(
            SCITEX_PROJECT_PROVIDER="scitex_sdk.local.LocalProjectProvider",
            SCITEX_PROJECT_STORAGE="scitex_sdk.local.LocalProjectStorage",
            SCITEX_LOCAL_PROJECT_ROOT=str(tmp_path),
        ):
            return project_file(req)

    return root, request


def test_text_preview_response(preview):
    root, request = preview
    (root / "notes.txt").write_text("Synthetic UTF-8: α", encoding="utf-8")
    response = request("notes.txt")
    assert response.status_code == 200
    assert json.loads(response.content) == {"success": True, "content": "Synthetic UTF-8: α"}


@pytest.mark.parametrize("extension,format_,mime", [
    ("png", "PNG", "image/png"),
    ("jpg", "JPEG", "image/jpeg"),
    ("jpeg", "JPEG", "image/jpeg"),
    ("webp", "WEBP", "image/webp"),
])
def test_existing_image_formats_stream(preview, extension, format_, mime):
    from PIL import Image

    root, request = preview
    path = root / ("plot." + extension)
    Image.new("RGB", (2, 2), "white").save(path, format=format_)
    expected = path.read_bytes()
    response = request(path.name, raw="true")
    try:
        assert response.status_code == 200
        assert response["Content-Type"] == mime
        assert b"".join(response.streaming_content) == expected
    finally:
        response.close()


@pytest.mark.parametrize("kind,status", [("missing", 404), ("directory", 404), ("oversized", 413), ("binary", 400)])
def test_preview_failures_keep_status_codes(preview, kind, status):
    from scitex_clew._django.services.project_files import MAX_TEXT_BYTES

    root, request = preview
    path = root / "entry"
    if kind == "directory":
        path.mkdir()
    elif kind == "oversized":
        with path.open("wb") as stream:
            stream.truncate(MAX_TEXT_BYTES + 1)
    elif kind == "binary":
        path.write_bytes(b"\xff")
    response = request("entry")
    assert response.status_code == status
    assert json.loads(response.content)["success"] is False


def test_internal_alias_preview(preview):
    root, request = preview
    target = root / ".scitex" / "writer"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("Synthetic alias preview")
    (root / "paper").symlink_to(".scitex/writer", target_is_directory=True)
    response = request("paper/notes.txt")
    assert response.status_code == 200
    assert json.loads(response.content)["content"] == "Synthetic alias preview"


def test_external_target_alias_is_rejected(preview):
    root, request = preview
    sibling = root.parent / "sibling.txt"
    sibling.write_text("Synthetic sibling fixture")
    (root / "external.txt").symlink_to(sibling)
    response = request("external.txt")
    assert response.status_code == 400
    assert "Synthetic sibling fixture" not in response.content.decode()


def test_raw_unknown_format_keeps_error(preview):
    root, request = preview
    (root / "notes.txt").write_text("Synthetic text")
    response = request("notes.txt", raw="true")
    assert response.status_code == 400
    assert json.loads(response.content)["error"] == "Unsupported image format"
