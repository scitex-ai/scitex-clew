"""Clew UI and workspace context are owned by the leaf package."""

from django.shortcuts import render
from scitex_sdk.app import embed
from scitex_sdk.host import AccessError, CapabilityUnavailable, project_access
from scitex_sdk.ui import branding, mount

from . import api, registry


def build_context(request, current_project=None):
    context = {
        **branding.shell_context(
            "Clew",
            accent="clew",
            panes={"ai": "unused", "files": "unused", "viewer": "unused"},
        ),
        **mount.mount_context(request),
        "module_name": "Clew",
        "module_icon": "fa-check-circle",
        "stx_mount": embed.mount_prefix(request),
        "clew_version": embed.package_version("scitex-clew"),
    }
    try:
        project = project_access(request)
        context.update(clew_project_id=project.id, clew_project_name=project.name)
    except (AccessError, CapabilityUnavailable) as exc:
        context["clew_project_error"] = str(exc)
    return context


def clew_index(request):
    return render(request, "clew_app/index.html", build_context(request))


__all__ = ["api", "build_context", "clew_index", "registry"]
