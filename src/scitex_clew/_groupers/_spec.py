"""Dict/JSON/YAML spec → grouper callable resolver.

Used by file config, CLI, and MCP so all three accept the same shape::

    {"type": "compose", "steps": [
        {"type": "pattern", "regex": "P\\d{2}"},
        {"type": "directory", "depth": 2, "min_size": 10}
    ]}

``{"type": "custom", "import": "mypkg.mod:fn"}`` is the escape hatch; not
honored in MCP mode.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from ._builtins import (
    auto,
    compose,
    directory_grouper,
    drop_all_files,
    identity,
    pattern_grouper,
    session_bundle_grouper,
)

_REGISTRY: dict[str, Callable[..., Callable]] = {
    "identity": identity,
    "drop_all_files": drop_all_files,
    "pattern": pattern_grouper,
    "directory": directory_grouper,
    "session_bundle": session_bundle_grouper,
    "auto": auto,
}


def register_grouper(name: str, factory: Callable[..., Callable]) -> None:
    """Register a custom built-in grouper factory under ``name``."""
    _REGISTRY[name] = factory


def resolve_spec(spec: Any, *, allow_custom: bool = True) -> Callable:
    """Return a grouper callable for ``spec``.

    ``spec`` may be:
      - already callable (returned as-is)
      - ``None`` → ``auto()``
      - ``{"type": "...", **kwargs}`` dict
      - ``{"type": "compose", "steps": [<spec>, ...]}``
      - ``{"type": "custom", "import": "pkg.mod:fn"}`` if ``allow_custom``
    """
    if spec is None:
        return auto()
    if callable(spec):
        return spec
    if not isinstance(spec, dict):
        raise TypeError(f"Grouper spec must be dict|callable|None, got {type(spec)}")

    kind = spec.get("type")
    if kind is None:
        raise ValueError(f"Grouper spec missing 'type': {spec}")

    if kind == "compose":
        steps = [resolve_spec(s, allow_custom=allow_custom) for s in spec.get("steps", [])]
        return compose(*steps)

    if kind == "custom":
        if not allow_custom:
            raise PermissionError("custom groupers are disabled in this context")
        target = spec["import"]
        module_name, _, attr = target.partition(":")
        mod = importlib.import_module(module_name)
        fn = getattr(mod, attr) if attr else mod
        return fn() if callable(fn) and not _looks_like_grouper(fn) else fn

    if kind in _REGISTRY:
        kwargs = {k: v for k, v in spec.items() if k != "type"}
        return _REGISTRY[kind](**kwargs)

    raise ValueError(f"Unknown grouper type: {kind!r}. Known: {list(_REGISTRY)}")


def _looks_like_grouper(fn) -> bool:
    """Heuristic: grouper factories take no args and return a callable."""
    try:
        import inspect

        sig = inspect.signature(fn)
        return len(sig.parameters) == 0
    except (TypeError, ValueError):
        return False
