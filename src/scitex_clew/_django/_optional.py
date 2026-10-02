"""Actionable optional GUI dependency failures; internal import bugs propagate."""

from typing import NoReturn


def gui_dependency_error(error: ModuleNotFoundError) -> NoReturn:
    if error.name not in {"django", "scitex_sdk", "scitex_logging", "psycopg"}:
        raise error
    raise ModuleNotFoundError(
        'The Clew GUI requires optional dependencies. '
        'Install with: pip install "scitex-clew[gui]" (scitex-sdk>=0.3.0).',
        name=error.name,
    ) from error
