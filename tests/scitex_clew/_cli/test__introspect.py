"""Tests for ``scitex_clew._cli._introspect`` (Python-API tree introspection)."""

from __future__ import annotations

import json
import types

import pytest

# PA-303: click is in the [cli] extra (not [project] deps).
CliRunner = pytest.importorskip("click.testing").CliRunner

from scitex_clew._cli._introspect import (
    TYPE_COLORS,
    _format_python_signature,
    _get_api_tree,
    list_python_apis,
)


# ----- TYPE_COLORS palette ------------------------------------------------- #


def test_type_colors_covers_module_class_func_var():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert set(TYPE_COLORS.keys()) == {"M", "C", "F", "V"}


# ----- _format_python_signature ------------------------------------------- #


def test_format_signature_unannotated_function_f_in_name_s():
    # Arrange
    # Arrange
    # Arrange
    def f(x, y):
        return x + y
    # Act
    # Act
    name_s, sig_s = _format_python_signature(f, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "f" in name_s  # may include ANSI codes


def test_format_signature_unannotated_function_x_in_sig_s_and_y_in_sig_s():
    # Arrange
    # Arrange
    # Arrange
    def f(x, y):
        return x + y
    # Act
    # Act
    name_s, sig_s = _format_python_signature(f, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "x" in sig_s and "y" in sig_s




def test_format_signature_with_annotations_and_defaults_x_in_sig_s_and_int_in_sig_s():
    # Arrange
    # Arrange
    # Arrange
    def f(x: int, name: str = "alice"):  # noqa: F841
        ...
    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "x" in sig_s and "int" in sig_s


def test_format_signature_with_annotations_and_defaults_name_in_sig_s_and_str_in_sig_s():
    # Arrange
    # Arrange
    # Arrange
    def f(x: int, name: str = "alice"):  # noqa: F841
        ...
    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "name" in sig_s and "str" in sig_s


def test_format_signature_with_annotations_and_defaults_alice_in_sig_s():
    # Arrange
    # Arrange
    # Arrange
    def f(x: int, name: str = "alice"):  # noqa: F841
        ...
    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "'alice'" in sig_s




def test_format_signature_with_return_annotation():
    # Arrange
    # Arrange
    def f() -> bool:
        return True

    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=False)
    # Assert
    # Assert
    assert "->" in sig_s and "bool" in sig_s


def test_format_signature_long_default_truncated():
    # Arrange
    # Arrange
    def f(x="x" * 50):  # noqa: F841
        ...

    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=False)
    # repr() longer than 20 chars is truncated to ellipsis.
    # Assert
    # Assert
    assert "..." in sig_s


def test_format_signature_multiline_emits_newlines_for_many_params():
    # Arrange
    # Arrange
    def f(a, b, c, d, e):  # noqa: F841
        ...

    # Act
    # Act
    _, sig_s = _format_python_signature(f, multiline=True)
    # Assert
    # Assert
    assert "\n" in sig_s


def test_format_signature_handles_builtins_gracefully_len_in_name_s():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    name_s, sig_s = _format_python_signature(len, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert "len" in name_s


def test_format_signature_handles_builtins_gracefully_sig_s_is_str():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    name_s, sig_s = _format_python_signature(len, multiline=False)
    # Act
    # Assert
    # Assert
    # Assert
    assert isinstance(sig_s, str)




# ----- _get_api_tree ------------------------------------------------------- #


def test_get_api_tree_records_module_root_len_rows_is_1():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    # Assert
    assert len(rows) == 1


def test_get_api_tree_records_module_root_root_type_m_len_rows_is_1():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    assert len(rows) == 1


def test_get_api_tree_records_module_root_root_type_m_root_type_m():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Assert
    assert len(rows) == 1
    root = rows[0]
    # Act
    # Assert
    assert root["Type"] == "M"




def test_get_api_tree_records_module_root_root_depth_0_len_rows_is_1():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    assert len(rows) == 1


def test_get_api_tree_records_module_root_root_depth_0_root_depth_0():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Assert
    assert len(rows) == 1
    root = rows[0]
    # Act
    # Assert
    assert root["Depth"] == 0




def test_get_api_tree_records_module_root_root_name_alpha_len_rows_is_1():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    assert len(rows) == 1


def test_get_api_tree_records_module_root_root_name_alpha_root_name_alpha():
    # Arrange
    # Arrange
    mod = types.ModuleType("alpha")
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Assert
    assert len(rows) == 1
    root = rows[0]
    # Act
    # Assert
    assert root["Name"] == "alpha"






def test_get_api_tree_descends_via_dunder_all_f_in_types_seen():
    # Arrange
    # Arrange
    # Arrange
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
    # Act
    # Act
    types_seen = {r["Type"] for r in rows[1:]}  # skip module row
    # Act
    # Assert
    # Assert
    # Assert
    assert "F" in types_seen


def test_get_api_tree_descends_via_dunder_all_c_in_types_seen():
    # Arrange
    # Arrange
    # Arrange
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
    # Act
    # Act
    types_seen = {r["Type"] for r in rows[1:]}  # skip module row
    # Act
    # Assert
    # Assert
    # Assert
    assert "C" in types_seen


def test_get_api_tree_descends_via_dunder_all_v_in_types_seen():
    # Arrange
    # Arrange
    # Arrange
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
    # Act
    # Act
    types_seen = {r["Type"] for r in rows[1:]}  # skip module row
    # Act
    # Assert
    # Assert
    # Assert
    assert "V" in types_seen


def test_get_api_tree_descends_via_dunder_all_not_any_private_in_r_name_for_r_in_rows():
    # Arrange
    # Arrange
    # Arrange
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
    # Act
    # Act
    types_seen = {r["Type"] for r in rows[1:]}  # skip module row
    # Act
    # Assert
    # Assert
    # Assert
    assert not any("_private" in r["Name"] for r in rows)




def test_get_api_tree_respects_max_depth_len_rows_shallow_is_1():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("c0")
    sub = types.ModuleType("c0.c1")
    sub.fn = lambda: None  # type: ignore[attr-defined]
    sub.__all__ = ["fn"]
    mod.c1 = sub  # type: ignore[attr-defined]
    mod.__all__ = ["c1"]
    # Act
    # Act
    rows_shallow = _get_api_tree(mod, max_depth=0)
    # Act
    # Assert
    # Assert
    # Assert
    assert len(rows_shallow) == 1


def test_get_api_tree_respects_max_depth_len_rows_deep_1_len_rows_shallow_is_1():
    # Arrange
    # Arrange
    mod = types.ModuleType("c0")
    sub = types.ModuleType("c0.c1")
    sub.fn = lambda: None  # type: ignore[attr-defined]
    sub.__all__ = ["fn"]
    mod.c1 = sub  # type: ignore[attr-defined]
    mod.__all__ = ["c1"]
    # Act
    rows_shallow = _get_api_tree(mod, max_depth=0)
    # Act
    # Assert
    # Assert
    assert len(rows_shallow) == 1


def test_get_api_tree_respects_max_depth_len_rows_deep_1_len_rows_deep_1():
    # Arrange
    # Arrange
    mod = types.ModuleType("c0")
    sub = types.ModuleType("c0.c1")
    sub.fn = lambda: None  # type: ignore[attr-defined]
    sub.__all__ = ["fn"]
    mod.c1 = sub  # type: ignore[attr-defined]
    mod.__all__ = ["c1"]
    # Act
    rows_shallow = _get_api_tree(mod, max_depth=0)
    # Only root row at max_depth=0.
    # Assert
    assert len(rows_shallow) == 1
    rows_deep = _get_api_tree(mod, max_depth=3)
    # Act
    # Assert
    assert len(rows_deep) > 1






def test_get_api_tree_skips_private_when_no_dunder_all_any_public_in_r_name_for_r_in_rows():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("d0")
    mod.public = 1  # type: ignore[attr-defined]
    mod._hidden = 2  # type: ignore[attr-defined]
    # Act
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    # Assert
    assert any("public" in r["Name"] for r in rows)


def test_get_api_tree_skips_private_when_no_dunder_all_not_any_hidden_in_r_name_for_r_in_rows():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("d0")
    mod.public = 1  # type: ignore[attr-defined]
    mod._hidden = 2  # type: ignore[attr-defined]
    # Act
    # Act
    rows = _get_api_tree(mod, max_depth=2)
    # Act
    # Assert
    # Assert
    # Assert
    assert not any("_hidden" in r["Name"] for r in rows)




def test_get_api_tree_with_docstring_flag_alpha_module_in_docs():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("e0")
    mod.__doc__ = "alpha module"
    def f():
        """fn-doc"""
    mod.f = f  # type: ignore[attr-defined]
    mod.__all__ = ["f"]
    rows = _get_api_tree(mod, max_depth=2, docstring=True)
    # Act
    # Act
    docs = [r["Docstring"] for r in rows]
    # Act
    # Assert
    # Assert
    # Assert
    assert "alpha module" in docs


def test_get_api_tree_with_docstring_flag_fn_doc_in_docs():
    # Arrange
    # Arrange
    # Arrange
    mod = types.ModuleType("e0")
    mod.__doc__ = "alpha module"
    def f():
        """fn-doc"""
    mod.f = f  # type: ignore[attr-defined]
    mod.__all__ = ["f"]
    rows = _get_api_tree(mod, max_depth=2, docstring=True)
    # Act
    # Act
    docs = [r["Docstring"] for r in rows]
    # Act
    # Assert
    # Assert
    # Assert
    assert "fn-doc" in docs




def test_get_api_tree_visited_set_breaks_cycles():
    """Self-referential modules don't loop forever."""
    # Arrange
    mod = types.ModuleType("loop")
    mod.self = mod  # type: ignore[attr-defined]
    mod.__all__ = ["self"]
    # Should return without recursion error.
    # Act
    rows = _get_api_tree(mod, max_depth=10)
    # Assert
    assert isinstance(rows, list)


# ----- list_python_apis CLI ------------------------------------------------ #


def test_list_python_apis_json_invocation_returns_zero_result_exit_code_equals_n_0():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    # Act
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Act
    # Assert
    # Assert
    # Assert
    assert result.exit_code == 0


def test_list_python_apis_json_invocation_returns_zero_payload_is_list_result_exit_code_equals_n_0():
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Act
    # Assert
    # Assert
    assert result.exit_code == 0


def test_list_python_apis_json_invocation_returns_zero_payload_is_list_payload_is_list():
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Assert
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # Act
    # Assert
    assert isinstance(payload, list)




def test_list_python_apis_json_invocation_returns_zero_len_payload_1_result_exit_code_equals_n_0():
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Act
    # Assert
    # Assert
    assert result.exit_code == 0


def test_list_python_apis_json_invocation_returns_zero_len_payload_1_len_payload_1():
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Assert
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # Act
    # Assert
    assert len(payload) >= 1






def test_list_python_apis_human_legend_present_result_exit_code_equals_n_0():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    # Act
    result = runner.invoke(list_python_apis, ["--root-only"])
    # Act
    # Assert
    # Assert
    # Assert
    assert result.exit_code == 0


def test_list_python_apis_human_legend_present_legend_in_result_output():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    # Act
    result = runner.invoke(list_python_apis, ["--root-only"])
    # Act
    # Assert
    # Assert
    # Assert
    assert "Legend:" in result.output




def test_list_python_apis_root_only_limits_depth_deep_exit_code_equals_n_0_and_shallow_exit_code_0():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    deep = runner.invoke(list_python_apis, ["--json"])
    # Act
    # Act
    shallow = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Act
    # Assert
    # Assert
    # Assert
    assert deep.exit_code == 0 and shallow.exit_code == 0


def test_list_python_apis_root_only_limits_depth_shallow_n_deep_n_deep_exit_code_equals_n_0_and_shallow_exit_code_0():
    # Arrange
    # Arrange
    runner = CliRunner()
    deep = runner.invoke(list_python_apis, ["--json"])
    # Act
    shallow = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Act
    # Assert
    # Assert
    assert deep.exit_code == 0 and shallow.exit_code == 0


def test_list_python_apis_root_only_limits_depth_shallow_n_deep_n_shallow_n_deep_n():
    # Arrange
    # Arrange
    runner = CliRunner()
    deep = runner.invoke(list_python_apis, ["--json"])
    # Act
    shallow = runner.invoke(list_python_apis, ["--json", "--root-only"])
    # Assert
    assert deep.exit_code == 0 and shallow.exit_code == 0
    deep_n = len(json.loads(deep.output))
    shallow_n = len(json.loads(shallow.output))
    # Act
    # Assert
    assert shallow_n <= deep_n






def test_list_python_apis_help_includes_examples_result_exit_code_equals_n_0():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    # Act
    result = runner.invoke(list_python_apis, ["--help"])
    # Act
    # Assert
    # Assert
    # Assert
    assert result.exit_code == 0


def test_list_python_apis_help_includes_examples_examples_in_result_output():
    # Arrange
    # Arrange
    # Arrange
    runner = CliRunner()
    # Act
    # Act
    result = runner.invoke(list_python_apis, ["--help"])
    # Act
    # Assert
    # Assert
    # Assert
    assert "Examples" in result.output


