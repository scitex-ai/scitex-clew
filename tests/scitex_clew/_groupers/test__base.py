"""Tests for ``scitex_clew._groupers._base`` (FileEntry, Group, merkle_root)."""

from __future__ import annotations

import pytest

from scitex_clew._groupers._base import FileEntry, Group, merkle_root


# ----- FileEntry ----------------------------------------------------------- #


def test_file_entry_holds_metadata():
    e = FileEntry(path="/a/b.txt", hash="deadbeef", role="input", session_id="s1")
    assert e.path == "/a/b.txt"
    assert e.hash == "deadbeef"
    assert e.role == "input"
    assert e.session_id == "s1"


def test_file_entry_is_frozen():
    """@dataclass(frozen=True) — assigning to a field must raise."""
    e = FileEntry(path="/x", hash="00", role="input", session_id="s")
    with pytest.raises(Exception):
        e.path = "/y"  # type: ignore[misc]


def test_file_entry_hashable_for_set_membership():
    """Frozen dataclasses can live in sets — exercise that contract."""
    e1 = FileEntry(path="/x", hash="00", role="input", session_id="s")
    e2 = FileEntry(path="/x", hash="00", role="input", session_id="s")
    assert {e1, e2} == {e1}


# ----- merkle_root --------------------------------------------------------- #


def test_merkle_root_empty_list():
    assert merkle_root([]) == ""


def test_merkle_root_single_element_returns_itself():
    assert merkle_root(["abc123"]) == "abc123"


def test_merkle_root_order_independence():
    """Sorting inside merkle_root means input order shouldn't matter."""
    a = "00" * 32
    b = "11" * 32
    c = "22" * 32
    assert merkle_root([a, b, c]) == merkle_root([c, a, b])


def test_merkle_root_changes_when_member_changes():
    a = "00" * 32
    b = "11" * 32
    a_prime = "ff" * 32
    assert merkle_root([a, b]) != merkle_root([a_prime, b])


def test_merkle_root_is_hex_string():
    h = merkle_root(["00" * 32, "11" * 32])
    assert all(c in "0123456789abcdef" for c in h)
    assert len(h) == 64  # sha256 = 32 bytes = 64 hex chars


def test_merkle_root_handles_non_hex_member_strings():
    """`_is_hex` falls back to utf-8 encoding for non-hex inputs."""
    h = merkle_root(["plain-text-1", "plain-text-2"])
    assert isinstance(h, str) and len(h) == 64


# ----- Group --------------------------------------------------------------- #


def test_group_size_reflects_members():
    members = [
        FileEntry(path=f"/f{i}", hash=f"{i:064x}", role="input", session_id="s")
        for i in range(5)
    ]
    g = Group(members=members, label="batch1", kind="bundle")
    assert g.size == 5


def test_group_role_is_unique_when_members_share_role():
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="input", session_id="s"),
    ]
    g = Group(members=members, label="x", kind="x")
    assert g.role == "input"


def test_group_role_is_mixed_for_heterogeneous_members():
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="output", session_id="s"),
    ]
    g = Group(members=members, label="x", kind="x")
    assert g.role == "mixed"


def test_group_root_hash_auto_computed_from_members():
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
        FileEntry(path="/b", hash="11" * 32, role="input", session_id="s"),
    ]
    g = Group(members=members, label="x", kind="x")
    expected = merkle_root([m.hash for m in members])
    assert g.root_hash == expected


def test_group_explicit_root_hash_kept():
    """Caller-provided root_hash overrides auto-derivation."""
    members = [
        FileEntry(path="/a", hash="00" * 32, role="input", session_id="s"),
    ]
    g = Group(members=members, label="x", kind="x", root_hash="ff" * 32)
    assert g.root_hash == "ff" * 32


def test_empty_group_root_hash_is_empty_string():
    g = Group(members=[], label="empty", kind="bundle")
    assert g.root_hash == ""


def test_group_root_hash_invariant_to_member_order():
    a = FileEntry(path="/a", hash="00" * 32, role="i", session_id="s")
    b = FileEntry(path="/b", hash="11" * 32, role="i", session_id="s")
    g_ab = Group(members=[a, b], label="x", kind="x")
    g_ba = Group(members=[b, a], label="x", kind="x")
    assert g_ab.root_hash == g_ba.root_hash
