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



@pytest.fixture
def text_response(preview):
    root, request = preview
    (root / "notes.txt").write_text("Synthetic UTF-8: α", encoding="utf-8")
    return request("notes.txt")


def test_text_preview_preserves_success_status(text_response):
    # Arrange
    # Act
    # Assert
    assert text_response.status_code == 200


def test_text_preview_preserves_utf8_payload(text_response):
    # Arrange
    # Act
    # Assert
    assert json.loads(text_response.content) == {"success": True, "content": "Synthetic UTF-8: α"}


@pytest.fixture(params=[("png", "PNG", "image/png"), ("jpg", "JPEG", "image/jpeg"), ("jpeg", "JPEG", "image/jpeg"), ("webp", "WEBP", "image/webp")])
def image_response(preview, request):
    from PIL import Image
    root, preview_request = preview
    extension, format_, mime = request.param
    path = root / ("plot." + extension)
    Image.new("RGB", (2, 2), "white").save(path, format=format_)
    expected = path.read_bytes()
    response = preview_request(path.name, raw="true")
    try:
        yield response, mime, expected
    finally:
        response.close()


def test_existing_image_formats_preserve_status(image_response):
    # Arrange
    response, mime, expected = image_response
    # Act
    # Assert
    assert response.status_code == 200


def test_existing_image_formats_preserve_mime(image_response):
    # Arrange
    response, mime, expected = image_response
    # Act
    # Assert
    assert response["Content-Type"] == mime


def test_existing_image_formats_preserve_stream_bytes(image_response):
    # Arrange
    response, mime, expected = image_response
    # Act
    # Assert
    assert b"".join(response.streaming_content) == expected


@pytest.fixture(params=[("missing", 404), ("directory", 404), ("oversized", 413), ("binary", 400)])
def failed_response(preview, request):
    from scitex_clew._django.services.project_files import MAX_TEXT_BYTES
    root, preview_request = preview
    kind, status = request.param
    path = root / "entry"
    if kind == "directory":
        path.mkdir()
    elif kind == "oversized":
        with path.open("wb") as stream:
            stream.truncate(MAX_TEXT_BYTES + 1)
    elif kind == "binary":
        path.write_bytes(b"\xff")
    yield preview_request("entry"), status


def test_preview_failures_preserve_status_codes(failed_response):
    # Arrange
    response, status = failed_response
    # Act
    # Assert
    assert response.status_code == status


def test_preview_failures_preserve_failure_payload(failed_response):
    # Arrange
    response, status = failed_response
    # Act
    # Assert
    assert json.loads(response.content)["success"] is False


@pytest.fixture
def alias_response(preview):
    root, request = preview
    target = root / ".scitex" / "writer"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("Synthetic alias preview")
    (root / "paper").symlink_to(".scitex/writer", target_is_directory=True)
    return request("paper/notes.txt")


def test_internal_alias_preserves_success_status(alias_response):
    # Arrange
    response = alias_response
    # Act
    # Assert
    assert response.status_code == 200


def test_internal_alias_preserves_preview_content(alias_response):
    # Arrange
    response = alias_response
    # Act
    # Assert
    assert json.loads(response.content)["content"] == "Synthetic alias preview"


@pytest.fixture
def external_response(preview):
    root, request = preview
    sibling = root.parent / "sibling.txt"
    sibling.write_text("Synthetic sibling fixture")
    (root / "external.txt").symlink_to(sibling)
    return request("external.txt")


def test_external_alias_preserves_denied_status(external_response):
    # Arrange
    response = external_response
    # Act
    # Assert
    assert response.status_code == 400


def test_external_alias_never_exposes_sibling_content(external_response):
    # Arrange
    response = external_response
    # Act
    # Assert
    assert "Synthetic sibling fixture" not in response.content.decode()


@pytest.fixture
def unsupported_response(preview):
    root, request = preview
    (root / "notes.txt").write_text("Synthetic text")
    return request("notes.txt", raw="true")


def test_raw_unknown_format_preserves_denied_status(unsupported_response):
    # Arrange
    response = unsupported_response
    # Act
    # Assert
    assert response.status_code == 400


def test_raw_unknown_format_preserves_error_message(unsupported_response):
    # Arrange
    response = unsupported_response
    # Act
    # Assert
    assert json.loads(response.content)["error"] == "Unsupported image format"
