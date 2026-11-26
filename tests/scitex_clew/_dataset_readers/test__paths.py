"""Whether clew has a store scope for a project, answered without minting one."""

from __future__ import annotations

from scitex_clew._dataset_readers._paths import project_scope_exists
from scitex_clew._db._scope import project_id_path


def test_a_project_without_a_persisted_id_has_no_scope(tmp_path):
    # Arrange
    root = tmp_path
    # Act
    exists = project_scope_exists(root)
    # Assert
    assert exists is False


def test_a_persisted_id_is_a_scope(tmp_path):
    # Arrange
    path = project_id_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("clew-abc\n", encoding="utf-8")
    # Act
    exists = project_scope_exists(tmp_path)
    # Assert
    assert exists is True


def test_checking_writes_nothing(tmp_path):
    # Arrange
    root = tmp_path
    # Act
    project_scope_exists(root)
    # Assert
    assert list(root.iterdir()) == []
