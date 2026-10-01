"""Authenticated Clew reads with explicit project and tenant boundaries."""

from __future__ import annotations

from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from scitex_logging import getLogger

from ..services.project_store import (
    ClewRequestError,
    ClewUnavailable,
    execute,
    project_context,
    project_path,
)

logger = getLogger(__name__)


def read_endpoint(operation):
    def decorate(parameters):
        @wraps(parameters)
        @require_http_methods(["GET"])
        def view(request):
            try:
                context = project_context(request)
                data = execute(context, operation, parameters(request, context))
                return JsonResponse({"success": True, "data": data})
            except ClewRequestError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)}, status=exc.status
                )
            except ClewUnavailable as exc:
                return JsonResponse({"success": False, "error": str(exc)}, status=503)
            except Exception:  # noqa: BLE001 — sanitize errors at the HTTP/process boundary
                logger.error("Clew request failed: %s", operation)
                return JsonResponse(
                    {"success": False, "error": "Clew request failed"}, status=500
                )

        return view

    return decorate


def integer(request, name, default, minimum, maximum):
    try:
        value = int(request.GET.get(name, default))
        if not minimum <= value <= maximum:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ClewRequestError(f"Invalid parameter: {name}") from exc
    return value


@read_endpoint("status")
def verification_status(request, context):
    return {}


@read_endpoint("stats")
def database_stats(request, context):
    return {}


@read_endpoint("runs")
def list_runs(request, context):
    return {
        "limit": integer(request, "limit", 50, 1, 500),
        "offset": integer(request, "offset", 0, 0, 1_000_000),
        "status": request.GET.get("status"),
    }


@read_endpoint("chain")
def verify_chain(request, context):
    target = request.GET.get("target")
    if not target:
        raise ClewRequestError("Missing required parameter: target")
    return {"target": project_path(context["root"], target)}


@read_endpoint("run")
def verify_run(request, context):
    if request.GET.get("from_scratch", "false").lower() != "false":
        raise ClewRequestError(
            "Script execution requires a separate authorized job", 405
        )
    session_id = request.GET.get("session_id")
    if not session_id:
        raise ClewRequestError("Missing required parameter: session_id")
    return {"session_id": session_id}


def dag_parameters(request, context):
    mode = request.GET.get("path_mode", "name")
    if mode not in {"name", "relative", "absolute"}:
        raise ClewRequestError("Invalid parameter: path_mode")
    target = request.GET.get("target_file")
    return {
        "session_id": request.GET.get("session_id"),
        "path_mode": mode,
        "target_file": project_path(context["root"], target) if target else None,
    }


@read_endpoint("dag_json")
def get_dag_data(request, context):
    return dag_parameters(request, context)


@read_endpoint("mermaid")
def get_mermaid_dag(request, context):
    parameters = dag_parameters(request, context)
    targets = [
        value.strip()
        for value in request.GET.get("target_files", "").split(",")
        if value.strip()
    ]
    return {
        **parameters,
        "target_files": [project_path(context["root"], value) for value in targets]
        or None,
        "claims": request.GET.get("claims", "false").lower() == "true",
        "show_hashes": request.GET.get("show_hashes", "false").lower() == "true",
    }


@read_endpoint("claims")
def list_claims_view(request, context):
    file_path = request.GET.get("file_path")
    return {
        "file_path": project_path(context["root"], file_path) if file_path else None,
        "claim_type": request.GET.get("claim_type"),
        "status": request.GET.get("status"),
        "limit": integer(request, "limit", 100, 1, 500),
    }


@csrf_protect
@require_http_methods(["POST"])
def add_examples(request):
    """Only an editor may scaffold examples in the authorized owner's root."""
    from scitex_sdk.host import project_access

    try:
        project = project_access(request, write=True)
        dest = project.path("examples/clew")
    except ClewRequestError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=exc.status)
    except ClewUnavailable as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=503)
    import scitex_clew

    try:
        result = scitex_clew.init_examples(dest)
        return JsonResponse({"success": True, "data": result})
    except Exception:  # noqa: BLE001 — sanitize errors at the HTTP/process boundary
        logger.error("Clew example initialization failed")
        return JsonResponse(
            {"success": False, "error": "Example initialization failed"}, status=500
        )


@require_http_methods(["GET"])
def project_file(request):
    """Project file preview through the SDK's authorized storage capability."""
    from django.http import FileResponse
    from scitex_sdk.host import project_access

    try:
        project = project_access(request)
        value = request.GET.get("path")
        if not value:
            raise ClewRequestError("Missing required parameter: path")
        path = project.path(value)
        from ..services.project_files import open_project_file, read_project_text

        if request.GET.get("raw") == "true":
            kinds = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }
            image = open_project_file(project.root, path)
            try:
                kind = kinds.get(path.suffix.lower())
                if not kind:
                    raise ClewRequestError("Unsupported image format")
                return FileResponse(image, content_type=kind)
            except BaseException:
                image.close()
                raise
        return JsonResponse(
            {"success": True, "content": read_project_text(project.root, path)}
        )
    except ClewRequestError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=exc.status)
    except ClewUnavailable as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=503)
    except (OSError, UnicodeError):
        return JsonResponse(
            {"success": False, "error": "File cannot be previewed"}, status=400
        )
