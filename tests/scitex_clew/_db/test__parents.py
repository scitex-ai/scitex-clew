"""Tests for ``scitex_clew._db._parents`` (backward-compat shim)."""

from __future__ import annotations

from scitex_clew._db import _parents
from scitex_clew._db._chain import ChainMixin
from scitex_clew._db._parents import ParentsMixin


def test_parents_mixin_is_chain_mixin_alias():
    """The shim binds `ParentsMixin = ChainMixin`; same class object."""
    assert ParentsMixin is ChainMixin


def test_module_exports_only_parents_mixin():
    """`__all__` is the public API contract; nothing else should leak in."""
    assert _parents.__all__ == ["ParentsMixin"]


def test_parents_mixin_callable_inherits_chain_methods():
    """Callers can instantiate / subclass via the alias name."""

    class Adopter(ParentsMixin):
        pass

    assert issubclass(Adopter, ChainMixin)


def test_alias_resolution_idempotent_on_reimport():
    """Re-importing the shim must not produce a different binding."""
    from importlib import reload

    reloaded = reload(_parents)
    assert reloaded.ParentsMixin is ChainMixin
