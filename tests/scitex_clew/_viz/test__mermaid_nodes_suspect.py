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


def test_class_definitions_emits_file_suspect_amber_band():
    # Arrange — schema v1.3: suspect uses amber #d29922 (not old orange #FFD580)
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    suspect_lines = [ln for ln in lines if "file_suspect" in ln]
    assert (
        len(suspect_lines) == 1
        and "d29922" in suspect_lines[0].lower()
    )


def test_class_definitions_emits_suspect_script_class_amber_band():
    # Arrange — schema v1.3: suspect script class uses amber #d29922
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    suspect_script = [
        ln for ln in lines if "classDef suspect " in ln and "file_suspect" not in ln
    ]
    assert (
        len(suspect_script) == 1
        and "d29922" in suspect_script[0].lower()
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


def test_class_definitions_emits_exception_classDef_solid_no_dashes():
    # Arrange — schema v1.3: exception uses solid violet fill, no dashed border
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    exception_lines = [ln for ln in lines if "classDef exception" in ln]
    assert len(exception_lines) == 1 and "stroke-dasharray" not in exception_lines[0]


def test_class_definitions_exception_classDef_uses_violet_fill():
    # Arrange — schema v1.3: exception fill is violet #8250df
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    exception_lines = [ln for ln in lines if "classDef exception" in ln]
    assert len(exception_lines) == 1 and "8250df" in exception_lines[0].lower()


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


def test_add_script_node_exception_verified_label_no_glyph_icon():
    # Arrange — schema v1.3: no ⊘ EXCEPTION glyph in label; color conveys it
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

    # Assert — ⊘ EXCEPTION removed in v1.3 (color conveys exception status)
    assert len(lines) == 1 and "⊘ EXCEPTION" not in lines[0]


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


def test_add_script_node_exception_failed_no_glyph_icon():
    # Arrange — schema v1.3: even when the exception node fails, no ⊘ EXCEPTION glyph.
    # The COLOR (violet for exception class, red for failed class) conveys the state.
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

    # Assert — ⊘ EXCEPTION glyph removed in v1.3
    assert len(lines) == 1 and "⊘ EXCEPTION" not in lines[0]


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


# ----- Frozen / trusted-input file nodes ------------------------------------- #


def test_class_definitions_emits_file_frozen_classDef():
    # Arrange
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    frozen_lines = [ln for ln in lines if "classDef file_frozen" in ln]
    assert len(frozen_lines) == 1


def test_class_definitions_file_frozen_no_dashed_border():
    # Arrange — schema v1.3: frozen folds into verified green, no dashed border
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    frozen_lines = [ln for ln in lines if "classDef file_frozen" in ln]
    assert len(frozen_lines) == 1 and "stroke-dasharray" not in frozen_lines[0]


def test_add_file_nodes_frozen_file_uses_file_frozen_class(tmp_path):
    # Arrange — write a real file so verify_file_hash returns True (locally ok).
    # The frozen_files set tips it into the frozen band.
    from scitex_clew._hash import hash_file

    target = tmp_path / "huge.npz"
    target.write_bytes(b"4.1TB placeholder")
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
        role="input",
        frozen_files={str(target)},
    )

    # Assert
    node_decls = [ln for ln in out_lines if ":::" in ln]
    assert len(node_decls) == 1 and "file_frozen" in node_decls[0]


def test_add_file_nodes_frozen_file_no_frozen_glyph_icon(tmp_path):
    # Arrange — schema v1.3: frozen folds into verified green, no 🔒 FROZEN glyph
    from scitex_clew._hash import hash_file

    target = tmp_path / "huge2.npz"
    target.write_bytes(b"placeholder data")
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
        role="input",
        frozen_files={str(target)},
    )

    # Assert — 🔒 FROZEN glyph removed in v1.3 (color conveys frozen/verified state)
    node_line = " ".join(out_lines)
    assert "🔒" not in node_line and "🔒 FROZEN" not in node_line


def test_add_file_nodes_normal_file_not_in_frozen_files_uses_file_ok(tmp_path):
    # Arrange — default path: no frozen_files → must use file_ok (behavior-preservation).
    from scitex_clew._hash import hash_file

    target = tmp_path / "normal.csv"
    target.write_text("x\n1\n")
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
    assert len(node_decls) == 1 and "file_ok" in node_decls[0] and "file_frozen" not in node_decls[0]


def test_add_file_nodes_explicitly_failed_outranks_frozen(tmp_path):
    # Arrange — a file that is in BOTH failed_files (e.g. explicitly failed
    # by the caller from a prior chain-propagation pass) AND in frozen_files.
    # The explicit failure must win over the frozen trust (e.g. file gone).
    target = tmp_path / "bad.npz"
    target.write_bytes(b"content")
    stored_hash = "0" * 64
    files = {str(target): stored_hash}
    out_lines: list = []
    file_nodes: dict = {}

    # Act — pass the file in BOTH failed_files AND frozen_files.
    add_file_nodes(
        out_lines,
        script_id="script_0",
        files=files,
        file_nodes=file_nodes,
        show_hashes=False,
        path_mode="name",
        role="input",
        failed_files={str(target)},
        frozen_files={str(target)},
    )

    # Assert — explicit failure outranks frozen trust.
    node_decls = [ln for ln in out_lines if ":::" in ln]
    assert len(node_decls) == 1 and "file_bad" in node_decls[0] and "file_frozen" not in node_decls[0]


# ----- Schema v1.3 specific: 4-state color-only recolor -------------------- #


def test_v13_verified_classDef_uses_2da44e_fill():
    # Arrange — schema v1.3: verified nodes use #2da44e (green)
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    verified_lines = [ln for ln in lines if "classDef verified " in ln and "scratch" not in ln]
    assert len(verified_lines) == 1 and "2da44e" in verified_lines[0].lower()


def test_v13_failed_classDef_uses_cf222e_fill():
    # Arrange — schema v1.3: failed nodes use #cf222e (red)
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    failed_lines = [ln for ln in lines if "classDef failed " in ln]
    assert len(failed_lines) == 1 and "cf222e" in failed_lines[0].lower()


def test_v13_exception_classDef_uses_8250df_fill():
    # Arrange — schema v1.3: exception nodes use #8250df (violet)
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    exception_lines = [ln for ln in lines if "classDef exception" in ln]
    assert len(exception_lines) == 1 and "8250df" in exception_lines[0].lower()


def test_v13_file_frozen_classDef_uses_verified_green():
    # Arrange — schema v1.3: frozen folds into verified green #2da44e
    lines: list = []

    # Act
    append_class_definitions(lines)

    # Assert
    frozen_lines = [ln for ln in lines if "classDef file_frozen" in ln]
    assert len(frozen_lines) == 1 and "2da44e" in frozen_lines[0].lower()


def test_v13_exception_node_reason_text_still_present():
    # Arrange — schema v1.3: reason text still shown (no ⊘ EXCEPTION glyph)
    lines: list = []
    run = {
        "script_path": "/scripts/gpac.py",
        "script_hash": "ab" * 32,
        "provenance": "exception",
        "exception_reason": "4.1TB gPAC never re-run",
    }
    verification = _FakeVerification(verified=True, from_scratch=False)

    # Act
    add_script_node(
        lines,
        idx=0,
        sid="exception_reason_s1",
        run=run,
        verification=verification,
        path_mode="name",
        show_hashes=False,
        has_failed_input=False,
        has_suspect_input=False,
    )

    # Assert — reason text preserved, but no ⊘ glyph
    assert len(lines) == 1 and "4.1TB gPAC never re-run" in lines[0] and "⊘" not in lines[0]
