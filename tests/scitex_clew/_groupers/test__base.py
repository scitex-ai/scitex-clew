"""Tests for ``scitex_clew._groupers._base`` (FileEntry, Group, merkle_root)."""

from __future__ import annotations

import pytest

from scitex_clew._groupers._base import FileEntry, Group, merkle_root


# ----- FileEntry ----------------------------------------------------------- #


def test_file_entry_holds_metadata_e_path_equals_a_b_txt():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    e = FileEntry(path="/a/b.txt", hash="deadbeef", role="input", session_id="s1")
    # Act
    # Assert
    # Assert
    # Assert
    assert e.path == "/a/b.txt"


def test_file_entry_holds_metadata_e_hash_equals_deadbeef():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    e = FileEntry(path="/a/b.txt", hash="deadbeef", role="input", session_id="s1")
    # Act
    # Assert
    # Assert
    # Assert
    assert e.hash == "deadbeef"


def test_file_entry_holds_metadata_e_role_equals_input():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    e = FileEntry(path="/a/b.txt", hash="deadbeef", role="input", session_id="s1")
    # Act
    # Assert
    # Assert
    # Assert
    assert e.role == "input"


def test_file_entry_holds_metadata_e_session_id_equals_s1():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    e = FileEntry(path="/a/b.txt", hash="deadbeef", role="input", session_id="s1")
    # Act
    # Assert
    # Assert
    # Assert
    assert e.session_id == "s1"




def test_file_entry_is_frozen():
    """@dataclass(frozen=True) — assigning to a field must raise."""
    # Arrange
    # Act
    e = FileEntry(path="/x", hash="00", role="input", session_id="s")
    # Assert
    with pytest.raises(Exception):
        e.path = "/y"  # type: ignore[misc]


def test_file_entry_hashable_for_set_membership():
    """Frozen dataclasses can live in sets — exercise that contract."""
    # Arrange
    e1 = FileEntry(path="/x", hash="00", role="input", session_id="s")
    # Act
    e2 = FileEntry(path="/x", hash="00", role="input", session_id="s")
    # Assert
    assert {e1, e2} == {e1}


# ----- merkle_root --------------------------------------------------------- #


def test_merkle_root_empty_list():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert merkle_root([]) == ""


def test_merkle_root_single_element_returns_itself():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert merkle_root(["abc123"]) == "abc123"


def test_merkle_root_order_independence():
    """Sorting inside merkle_root means input order shouldn't matter."""
    # Arrange
    a = "00" * 32
    b = "11" * 32
    # Act
    c = "22" * 32
    # Assert
    assert merkle_root([a, b, c]) == merkle_root([c, a, b])


def test_merkle_root_changes_when_member_changes():
    # Arrange
    # Arrange
    a = "00" * 32
    b = "11" * 32
    # Act
    # Act
    a_prime = "ff" * 32
    # Assert
    # Assert
    assert merkle_root([a, b]) != merkle_root([a_prime, b])


def test_merkle_root_is_hex_string_all_c_in_0123456789abcdef_for_c_in_h():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    h = merkle_root(["00" * 32, "11" * 32])
    # Act
    # Assert
    # Assert
    # Assert
    assert all(c in "0123456789abcdef" for c in h)


def test_merkle_root_is_hex_string_len_h_is_64():
    # Arrange
    # Arrange
    # Act
    # Arrange
    # Act
    h = merkle_root(["00" * 32, "11" * 32])
    # Act
    # Assert
    # Assert
    # Assert
    assert len(h) == 64  # sha256 = 32 bytes = 64 hex chars




def test_merkle_root_handles_non_hex_member_strings():
    """`_is_hex` falls back to utf-8 encoding for non-hex inputs."""
    # Arrange
    # Act
    h = merkle_root(["plain-text-1", "plain-text-2"])
    # Assert
    assert isinstance(h, str) and len(h) == 64


# ----- Group --------------------------------------------------------------- #


def test_group_size_reflects_members():
    # Arrange
    # Arrange
    members = [
        FileEntry(path=f"/f{i}", hash=f"{i:064x}", role="input", session_id="s")
        for i in range(5)
    ]
    # Act
    # Act
    g = Group(members=members, label="batch1", kind="bundle")
    # Assert
    # Assert
    assert g.size == 5


def test_group_role_is_unique_when_members_share_role():
    # Arrange
    # Arrange
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="input", session_id="s"),
    ]
    # Act
    # Act
    g = Group(members=members, label="x", kind="x")
    # Assert
    # Assert
    assert g.role == "input"


def test_group_role_is_mixed_for_heterogeneous_members():
    # Arrange
    # Arrange
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="output", session_id="s"),
    ]
    # Act
    # Act
    g = Group(members=members, label="x", kind="x")
    # Assert
    # Assert
    assert g.role == "mixed"


def test_group_root_hash_auto_computed_from_members():
    # Arrange
    # Arrange
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="input", session_id="s"),
    ]
    g = Group(members=members, label="x", kind="x")
    # Act
    # Act
    expected = merkle_root([m.hash for m in members])
    # Assert
    # Assert
    assert g.root_hash == expected


def test_group_explicit_root_hash_kept():
    """Caller-provided root_hash overrides auto-derivation."""
    # Arrange
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
    ]
    # Act
    g = Group(members=members, label="x", kind="x", root_hash="ff" * 32)
    # Assert
    assert g.root_hash == "ff" * 32


def test_empty_group_root_hash_is_empty_string():
    # Arrange
    # Act
    # Arrange
    # Act
    g = Group(members=[], label="empty", kind="bundle")
    # Assert
    # Assert
    assert g.root_hash == ""


def test_group_root_hash_invariant_to_member_order():
    # Arrange
    # Arrange
    a = FileEntry(path="/a", hash="00" * 32, role="i", session_id="s")
    b = FileEntry(path="/b", hash="11" * 32, role="i", session_id="s")
    g_ab = Group(members=[a, b], label="x", kind="x")
    # Act
    # Act
    g_ba = Group(members=[b, a], label="x", kind="x")
    # Assert
    # Assert
    assert g_ab.root_hash == g_ba.root_hash
