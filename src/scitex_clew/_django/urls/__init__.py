"""Clew app URLs package.

Re-exports all URL patterns from submodules for Django URL configuration.
"""

from __future__ import annotations

try:
    from django.urls import include, path
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)

from .api import urlpatterns as api_patterns
from .index import urlpatterns as index_patterns

app_name = "clew_app"

# Combine: index pages at root, API under api/ prefix
urlpatterns = index_patterns + [
    path("api/", include(api_patterns)),
]


# EOF
