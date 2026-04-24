"""Data types for file grouping."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class FileEntry:
    """One tracked file with its recorded hash and role."""

    path: str
    hash: str
    role: str
    session_id: str


@dataclass
class Group:
    """A visual collapse of related FileEntry objects.

    ``root_hash`` is the Merkle root over member hashes, making group-level
    verification meaningful: a group is ✓ iff every member verifies.
    """

    members: list[FileEntry]
    label: str
    kind: str
    root_hash: str = ""

    def __post_init__(self) -> None:
        if not self.root_hash:
            self.root_hash = merkle_root([m.hash for m in self.members])

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def role(self) -> str:
        roles = {m.role for m in self.members}
        return roles.pop() if len(roles) == 1 else "mixed"


GroupOrEntry = Union[FileEntry, Group]


def merkle_root(hashes: list[str]) -> str:
    """Order-independent Merkle-style root over a list of hex hashes."""
    if not hashes:
        return ""
    if len(hashes) == 1:
        return hashes[0]
    h = hashlib.sha256()
    for x in sorted(hashes):
        h.update(bytes.fromhex(x) if _is_hex(x) else x.encode("utf-8"))
    return h.hexdigest()


def _is_hex(s: str) -> bool:
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False
