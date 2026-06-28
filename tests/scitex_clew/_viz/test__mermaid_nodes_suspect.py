"""Tests for ``VerificationStatus.SUSPECT`` plumbing in ``_viz/_mermaid_nodes``.

Covers the new ``suspect_files`` / ``has_suspect_input`` parameters on
the node-emission helpers. No DB, no on-disk hashing — we pass tiny
hand-rolled ``files`` dicts and lambda-fake verification objects so the
3-colour cascade is exercised on its own (PA-306 §1 DI-only).
"""

from __future__ import annotations

from typing import Any

from scitex_clew._viz._mermaid_nodes import (
    add_file_nodes,
    add_script_node,
    append_class_definitions,
)


class _FakeVerification:
    """Lightweight stand-in for ``RunVerification`` for the script-node tests.

    The renderer only reads ``.is_verified`` and ``.is_verified_from_scratch``
    so we keep this to two booleans.
    """

    def __init__(self, *, verified: bool, from_scratch: bool = False) -> None:
        self.is_verified = verified
        self.is_verified_from_scratch = from_scratch


# ----- classDef line ------------------------------------------------------- #


def test_class_definitions_emits_file_suspect_orange_band():
    # Arrange
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    suspect_lines = [ln for ln in lines if "file_suspect" in ln]
    assert (
        len(suspect_lines) == 1
        and "FFD580" in suspect_lines[0]
        and "FF8C00" in suspect_lines[0]
    )


def test_class_definitions_emits_suspect_script_class_orange_band():
    # Arrange
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    suspect_script = [
        ln for ln in lines if "classDef suspect " in ln and "file_suspect" not in ln
    ]
    assert (
        len(suspect_script) == 1
        and "FFD580" in suspect_script[0]
        and "FF8C00" in suspect_script[0]
    )


# ----- add_file_nodes ------------------------------------------------------ #


def test_add_file_nodes_uses_file_suspect_class_when_path_in_suspect_files(tmp_path):
    # Arrange — write a file whose canonical hash (via the renderer's own
    # ``hash_file`` helper, which is sha256[:32]) matches what we declare
    # as the stored hash; the file is locally OK. The renderer's ``verify_file_hash``
    # therefore returns True on its own check, so only ``suspect_files``
    # tips the cascade into the orange band.
    from scitex_clew._hash import hash_file

    target = tmp_path / "out.csv"
    target.write_text("hello\n")
    stored_hash = hash_file(str(target))
    files = {str(target): stored_hash}
    out_lines: list = []
    file_nodes: dict = {}

    # Act
    add_file_nodes(
        out_lines,
        script_id="script_0",
        files=files,
        file_nodes=file_nodes,
        show_hashes=False,
        path_mode="name",
        role="output",
        suspect_files={str(target)},
    )

    # Assert
    node_decls = [ln for ln in out_lines if ":::" in ln]
    assert (
        len(node_decls) == 1
        and "file_suspect" in node_decls[0]
        and "file_ok" not in node_decls[0]
    )


def test_add_file_nodes_falls_back_to_file_ok_when_suspect_files_empty(tmp_path):
    # Arrange — same fixture as above but no suspect_files; legacy
    # 2-colour behaviour must be preserved.
    from scitex_clew._hash import hash_file

    target = tmp_path / "out.csv"
    target.write_text("hello\n")
    stored_hash = hash_file(str(target))
    files = {str(target): stored_hash}
    out_lines: list = []
    file_nodes: dict = {}

    # Act
    add_file_nodes(
        out_lines,
        script_id="script_0",
        files=files,
        file_nodes=file_nodes,
        show_hashes=False,
        path_mode="name",
        role="output",
    )

    # Assert
    node_decls = [ln for ln in out_lines if ":::" in ln]
    assert (
        len(node_decls) == 1
        and "file_ok" in node_decls[0]
        and "file_suspect" not in node_decls[0]
    )


def test_add_file_nodes_local_failure_outranks_suspect_membership(tmp_path):
    # Arrange — file content does NOT match the stored hash, AND the path
    # is in suspect_files. Local-failed must win (red) over orange.
    target = tmp_path / "out.csv"
    target.write_text("hello\n")
    stored_hash = "0" * 64  # deliberately wrong, won't match content

    files = {str(target): stored_hash}
    out_lines: list = []
    file_nodes: dict = {}

    # Act
    add_file_nodes(
        out_lines,
        script_id="script_0",
        files=files,
        file_nodes=file_nodes,
        show_hashes=False,
        path_mode="name",
        role="output",
        suspect_files={str(target)},
    )

    # Assert
    node_decls = [ln for ln in out_lines if ":::" in ln]
    assert (
        len(node_decls) == 1
        and "file_bad" in node_decls[0]
        and "file_suspect" not in node_decls[0]
    )


# ----- add_script_node ----------------------------------------------------- #


def test_add_script_node_uses_suspect_class_when_has_suspect_input_true():
    # Arrange
    lines: list = []
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="s1",
        run={"script_path": "/scripts/run.py", "script_hash": "ab" * 32},
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=True,
    )

    # Assert
    assert (
        len(lines) == 1
        and ":::suspect" in lines[0]
        and ":::verified" not in lines[0]
    )


def test_add_script_node_failed_input_outranks_suspect_input():
    # Arrange — both flags True; the cascade must pick failed (red), not
    # suspect (orange).
    lines: list = []
    verification = _FakeVerification(verified=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="s1",
        run={"script_path": "/scripts/run.py", "script_hash": "ab" * 32},
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=True,
        has_suspect_input=True,
    )

    # Assert
    assert (
        len(lines) == 1
        and ":::failed" in lines[0]
        and ":::suspect" not in lines[0]
    )


# ----- Exception provenance marker ------------------------------------------ #


def test_class_definitions_emits_exception_classDef_with_dashed_style():
    # Arrange
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    exception_lines = [ln for ln in lines if "classDef exception" in ln]
    assert len(exception_lines) == 1 and "stroke-dasharray" in exception_lines[0]


def test_class_definitions_exception_classDef_uses_lavender_fill():
    # Arrange
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    exception_lines = [ln for ln in lines if "classDef exception" in ln]
    assert len(exception_lines) == 1 and "E6E6FA" in exception_lines[0]


def test_add_script_node_exception_verified_uses_exception_class():
    # Arrange — a verified exception node (no failure) must use the dashed
    # 'exception' class rather than 'verified'.
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "4.1TB gPAC, recipe-known, never re-run",
    }
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_s1",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and ":::exception" in lines[0]


def test_add_script_node_exception_verified_label_contains_badge():
    # Arrange
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "external job",
    }
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_s2",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and "⊘ EXCEPTION" in lines[0]


def test_add_script_node_exception_verified_label_contains_reason():
    # Arrange
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "4.1TB gPAC, recipe-known, never re-run",
    }
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_s3",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and "4.1TB gPAC, recipe-known, never re-run" in lines[0]


def test_add_script_node_exception_failed_uses_failed_class_not_exception():
    # Arrange — an exception node with a local failure must use 'failed', NOT
    # 'exception', so the DAG view does not lie about the failure.
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "external job",
    }
    verification = _FakeVerification(verified=False, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_fail_s1",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and ":::failed" in lines[0] and ":::exception" not in lines[0]


def test_add_script_node_exception_failed_still_shows_badge():
    # Arrange — even when the exception node fails, the ⊘ EXCEPTION badge
    # must still appear in the label (so the user knows it was hand-exception).
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "external job",
    }
    verification = _FakeVerification(verified=False, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_fail_s2",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and "⊘ EXCEPTION" in lines[0]


def test_add_script_node_tracked_verified_uses_verified_class_not_exception():
    # Arrange — a normal tracked verified node must NOT get the exception class;
    # behavior-preservation guarantee.
    lines: list = []
    run = {
        "script_path": "/scripts/normal.py",
        "script_hash": "ab" * 32,
        "provenance": "tracked",
        "exception_reason": None,
    }
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="tracked_s1",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert
    assert len(lines) == 1 and ":::verified" in lines[0] and ":::exception" not in lines[0]
