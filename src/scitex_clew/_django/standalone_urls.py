"""The leaf urlconf mounts unchanged at the standalone root."""

from django.urls import include, path
from scitex_sdk.ui import project_scope

from . import urls


def project_list(request):
    provider = project_scope.host_project_provider()
    return project_scope.project_listing_view(provider)(request)


urlpatterns = [
    path("project-list/", project_list, name="project-list"),
    path("", include(urls)),
]
