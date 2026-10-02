"""Clew app URLs - API endpoints."""

from __future__ import annotations

try:
    from django.urls import path
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)

from ..views import api, registry

# API patterns - thin wrappers around scitex.clew package
urlpatterns = [
    path("file/", api.project_file, name="clew_api_file"),
    # Verification status and statistics
    path("status/", api.verification_status, name="clew_api_status"),
    path("stats/", api.database_stats, name="clew_api_stats"),
    # Runs listing and verification
    path("runs/", api.list_runs, name="clew_api_runs"),
    path("verify-run/", api.verify_run, name="clew_api_verify_run"),
    # Chain verification
    path("verify-chain/", api.verify_chain, name="clew_api_verify_chain"),
    # DAG visualization data
    path("dag/json/", api.get_dag_data, name="clew_api_dag_json"),
    path("dag/mermaid/", api.get_mermaid_dag, name="clew_api_dag_mermaid"),
    # Claims
    path("claims/", api.list_claims_view, name="clew_api_claims"),
    # Example pipeline initialization
    path("add-examples/", api.add_examples, name="clew_api_add_examples"),
    # Clew Registry — hash registration and verification
    path("register/", registry.register_hash, name="clew_api_register"),
    path("verify/<str:hash_value>/", registry.verify_hash, name="clew_api_verify"),
]


# EOF
