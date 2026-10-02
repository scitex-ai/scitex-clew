"""The leaf urlconf mounts unchanged at the standalone root."""

try:
    from django.urls import include, path
    from scitex_sdk.ui import project_scope
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)

from . import urls


def project_list(request):
    provider = project_scope.host_project_provider()
    return project_scope.project_listing_view(provider)(request)


urlpatterns = [
    path("project-list/", project_list, name="project-list"),
    path("", include(urls)),
]
