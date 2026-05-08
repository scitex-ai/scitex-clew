"""Tests for ``scitex_clew._cli._introspect`` (Python-API tree introspection)."""

from __future__ import annotations

import json
import types

from click.testing import CliRunner

from scitex_clew._cli._introspect import (
    TYPE_COLORS,
    _format_python_signature,
    _get_api_tree,
    list_python_apis,
)


# ----- TYPE_COLORS palette ------------------------------------------------- #


def test_type_colors_covers_module_class_func_var():
    assert set(TYPE_COLORS.keys()) == {"M", "C", "F", "V"}


# ----- _format_python_signature ------------------------------------------- #


def test_format_signature_unannotated_function():
    def f(x, y):
        return x + y

    name_s, sig_s = _format_python_signature(f, multiline=False)
    assert "f" in name_s  # may include ANSI codes
    assert "x" in sig_s and "y" in sig_s


def test_format_signature_with_annotations_and_defaults():
    def f(x: int, name: str = "alice"):  # noqa: F841
        ...

    _, sig_s = _format_python_signature(f, multiline=False)
    assert "x" in sig_s and "int" in sig_s
    assert "name" in sig_s and "str" in sig_s
    assert "'alice'" in sig_s


def test_format_signature_with_return_annotation():
    def f() -> bool:
        return True

    _, sig_s = _format_python_signature(f, multiline=False)
    assert "->" in sig_s and "bool" in sig_s


def test_format_signature_long_default_truncated():
    def f(x="x" * 50):  # noqa: F841
        ...

    _, sig_s = _format_python_signature(f, multiline=False)
    # repr() longer than 20 chars is truncated to ellipsis.
    assert "..." in sig_s


def test_format_signature_multiline_emits_newlines_for_many_params():
    def f(a, b, c, d, e):  # noqa: F841
        ...

    _, sig_s = _format_python_signature(f, multiline=True)
    assert "\n" in sig_s


def test_format_signature_handles_builtins_gracefully():
    """`inspect.signature` can fail on some builtins — fall back cleanly."""
    name_s, sig_s = _format_python_signature(len, multiline=False)
    assert "len" in name_s
    # When inspect.signature fails, sig_s is the empty string (fallback path).
    assert isinstance(sig_s, str)


# ----- _get_api_tree ------------------------------------------------------- #


def test_get_api_tree_records_module_root():
    mod = types.ModuleType("alpha")
    rows = _get_api_tree(mod, max_depth=2)
    assert len(rows) == 1
    root = rows[0]
    assert root["Type"] == "M"
    assert root["Depth"] == 0
    assert root["Name"] == "alpha"


def test_get_api_tree_descends_via_dunder_all():
    mod = types.ModuleType("beta")

    def _fn(): ...

    class _Cls:
        pass

    mod.public_fn = _fn  # type: ignore[attr-defined]
    mod.public_cls = _Cls  # type: ignore[attr-defined]
    mod.LITERAL = 42  # type: ignore[attr-defined]
    mod._private = "hidden"  # type: ignore[attr-defined]
    mod.__all__ = ["public_fn", "public_cls", "LITERAL"]
    rows = _get_api_tree(mod, max_depth=3)
    types_seen = {r["Type"] for r in rows[1:]}  # skip module row
    # F, C, V should all be present; _private excluded.
    assert "F" in types_seen
    assert "C" in types_seen
    assert "V" in types_seen
    assert not any("_private" in r["Name"] for r in rows)


def test_get_api_tree_respects_max_depth():
    mod = types.ModuleType("c0")
    sub = types.ModuleType("c0.c1")
    sub.fn = lambda: None  # type: ignore[attr-defined]
    sub.__all__ = ["fn"]
    mod.c1 = sub  # type: ignore[attr-defined]
    mod.__all__ = ["c1"]
    rows_shallow = _get_api_tree(mod, max_depth=0)
    # Only root row at max_depth=0.
    assert len(rows_shallow) == 1
    rows_deep = _get_api_tree(mod, max_depth=3)
    assert len(rows_deep) > 1


def test_get_api_tree_skips_private_when_no_dunder_all():
    mod = types.ModuleType("d0")
    mod.public = 1  # type: ignore[attr-defined]
    mod._hidden = 2  # type: ignore[attr-defined]
    rows = _get_api_tree(mod, max_depth=2)
    assert any("public" in r["Name"] for r in rows)
    assert not any("_hidden" in r["Name"] for r in rows)


def test_get_api_tree_with_docstring_flag():
    mod = types.ModuleType("e0")
    mod.__doc__ = "alpha module"

    def f():
        """fn-doc"""

    mod.f = f  # type: ignore[attr-defined]
    mod.__all__ = ["f"]
    rows = _get_api_tree(mod, max_depth=2, docstring=True)
    docs = [r["Docstring"] for r in rows]
    assert "alpha module" in docs
    assert "fn-doc" in docs


def test_get_api_tree_visited_set_breaks_cycles():
    """Self-referential modules don't loop forever."""
    mod = types.ModuleType("loop")
    mod.self = mod  # type: ignore[attr-defined]
    mod.__all__ = ["self"]
    # Should return without recursion error.
    rows = _get_api_tree(mod, max_depth=10)
    assert isinstance(rows, list)


# ----- list_python_apis CLI ------------------------------------------------ #


def test_list_python_apis_json_invocation_returns_zero():
    runner = CliRunner()
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) >= 1


def test_list_python_apis_human_legend_present():
    runner = CliRunner()
    result = runner.invoke(list_python_apis, ["--root-only"])
    assert result.exit_code == 0
    # `Legend:` line is unconditional in the human output.
    assert "Legend:" in result.output


def test_list_python_apis_root_only_limits_depth():
    runner = CliRunner()
    deep = runner.invoke(list_python_apis, ["--json"])
    shallow = runner.invoke(list_python_apis, ["--json", "--root-only"])
    assert deep.exit_code == 0 and shallow.exit_code == 0
    deep_n = len(json.loads(deep.output))
    shallow_n = len(json.loads(shallow.output))
    assert shallow_n <= deep_n


def test_list_python_apis_help_includes_examples():
    runner = CliRunner()
    result = runner.invoke(list_python_apis, ["--help"])
    assert result.exit_code == 0
    assert "Examples" in result.output
