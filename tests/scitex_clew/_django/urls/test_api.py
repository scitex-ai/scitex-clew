"""Leaf API URL identity must remain the mounted leaf function."""


def test_preview_route_resolves_to_leaf_file_view():
    # Arrange
    import os
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scitex_clew._django.settings")
    django.setup()
    from scitex_clew._django.urls.api import urlpatterns
    from scitex_clew._django.views.api import project_file
    # Act
    route = next(pattern for pattern in urlpatterns if pattern.name == "clew_api_file")
    # Assert
    assert route.callback is project_file
