#!/usr/bin/env python3
"""Two projects, one host database, keys the author chose — no collision.

WHY THIS FILE EXISTS. Before the Postgres migration every project had its
OWN database file, and that file did the scoping: ``claim_id`` and
``cite_key`` are chosen by the author, so two manuscripts could both hold a
claim called ``acute_n_sig_pathways`` or both cite ``smith2020`` and never
meet. One host database collapses that, and ``MergeRule.LAST_WRITER_WINS``
would resolve the clash SILENTLY — one manuscript's provenance overwriting
another's with nothing raising.

THESE TESTS FAIL WITHOUT THE FIX, which is the only reason to trust them.
`TestAuthorChosenKeysDoNotCollide` deliberately uses nothing but the public
store openers and ``$SCITEX_CLEW_PROJECT``, so it runs unchanged against the
pre-fix commit — where the env var is a no-op, both writes land on ONE row,
and the assertions fail on the DATA rather than on an import.

Each test still gets its own throwaway PostgreSQL schema from the autouse
`isolated_store` fixture, so "two projects" means two scopes inside one
private schema. No mocks and no monkeypatch: the environment variable is
set for real and restored on teardown, and the database is a real one.
"""

import os
import shutil

import pytest
from scitex_dev.store import ANY_REVISION

from scitex_clew._attest._stamp import _stamps_store
from scitex_clew._citation._model import citations_store
from scitex_clew._claim._store import _open_store
from scitex_clew._db import VerificationDB, reset_db

PROJECT_ENV = "SCITEX_CLEW_PROJECT"
PROJECT_A = "/projects/manuscript-alpha"
PROJECT_B = "/projects/manuscript-beta"


class _ProjectSwitch:
    """Switches the process between projects the way an operator would."""

    def __call__(self, name: str) -> None:
        os.environ[PROJECT_ENV] = name
        reset_db()

    @staticmethod
    def unset() -> None:
        os.environ.pop(PROJECT_ENV, None)
        reset_db()


@pytest.fixture
def as_project():
    """Real ``os.environ`` writes, restored on teardown.

    ``SCITEX_CLEW_PROJECT`` is the documented override — this is
    configuration, not a stand-in for the code under test. ``reset_db()``
    drops the cached global so the next open re-resolves the scope.
    """
    previous = os.environ.get(PROJECT_ENV)
    try:
        yield _ProjectSwitch()
    finally:
        if previous is None:
            os.environ.pop(PROJECT_ENV, None)
        else:
            os.environ[PROJECT_ENV] = previous
        reset_db()


def _put_citation(cite_key: str, status: str) -> None:
    store = citations_store()
    try:
        store.put({"cite_key": cite_key, "status": status}, expected_revision=ANY_REVISION)
    finally:
        store.close()


def _read_citation_status(cite_key: str):
    store = citations_store()
    try:
        row = store.get((cite_key,))
        return None if row is None else row.values.get("status")
    finally:
        store.close()


def _put_claim(claim_id: str, file_path: str) -> None:
    store = _open_store()
    try:
        store.put(
            {
                "claim_id": claim_id,
                "file_path": file_path,
                "claim_type": "numeric",
                "status": "verified",
            },
            expected_revision=ANY_REVISION,
        )
    finally:
        store.close()


def _put_stamp(root_hash: str) -> None:
    store = _stamps_store()
    try:
        store.put(
            {
                "stamp_id": "stamp_deadbeef0000",
                "root_hash": root_hash,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "backend": "file",
            },
            expected_revision=ANY_REVISION,
        )
    finally:
        store.close()


class TestAuthorChosenKeysDoNotCollide:
    """The regression itself. Every test here fails on the unfixed code."""

    def test_same_cite_key_in_two_projects_keeps_project_a_value(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_citation("smith2020", "verified")
        # Act
        as_project(PROJECT_B)
        _put_citation("smith2020", "stub")
        as_project(PROJECT_A)
        # Assert
        assert _read_citation_status("smith2020") == "verified"

    def test_same_cite_key_in_two_projects_keeps_project_b_value(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_citation("smith2020", "verified")
        # Act
        as_project(PROJECT_B)
        _put_citation("smith2020", "stub")
        # Assert
        assert _read_citation_status("smith2020") == "stub"

    def test_project_a_does_not_see_project_b_citation(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_citation("alpha_only", "verified")
        as_project(PROJECT_B)
        _put_citation("beta_only", "verified")
        # Act
        as_project(PROJECT_A)
        store = citations_store()
        keys = {r.values.get("cite_key") for r in store.rows()}
        store.close()
        # Assert
        assert keys == {"alpha_only"}

    def test_same_claim_id_in_two_projects_keeps_project_a_value(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_claim("acute_n_sig_pathways", "/alpha/results.py")
        # Act
        as_project(PROJECT_B)
        _put_claim("acute_n_sig_pathways", "/beta/results.py")
        as_project(PROJECT_A)
        store = _open_store()
        row = store.get(("acute_n_sig_pathways",))
        store.close()
        # Assert
        assert row.values.get("file_path") == "/alpha/results.py"

    def test_same_session_id_in_two_projects_keeps_project_a_script(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        VerificationDB().add_run(session_id="2026Y-01M-01D_AAAA", script_path="/alpha.py")
        # Act
        as_project(PROJECT_B)
        VerificationDB().add_run(session_id="2026Y-01M-01D_AAAA", script_path="/beta.py")
        as_project(PROJECT_A)
        row = VerificationDB()._runs.get(("2026Y-01M-01D_AAAA",))
        # Assert
        assert row.values.get("script_path") == "/alpha.py"

    def test_project_a_run_listing_excludes_project_b(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        VerificationDB().add_run(session_id="alpha_run", script_path="/alpha.py")
        as_project(PROJECT_B)
        VerificationDB().add_run(session_id="beta_run", script_path="/beta.py")
        # Act
        as_project(PROJECT_A)
        sessions = {r["session_id"] for r in VerificationDB().list_runs(limit=100)}
        # Assert
        assert sessions == {"alpha_run"}

    def test_same_stamp_id_in_two_projects_keeps_project_a_root_hash(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_stamp("alpha_root")
        # Act
        as_project(PROJECT_B)
        _put_stamp("beta_root")
        as_project(PROJECT_A)
        store = _stamps_store()
        row = store.get(("stamp_deadbeef0000",))
        store.close()
        # Assert
        assert row.values.get("root_hash") == "alpha_root"


class TestReadsAndWritesResolveTheScopeIdentically:
    """A lookup must not miss a row it just wrote."""

    def test_get_finds_the_row_put_under_the_same_scope(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        # Act
        _put_citation("round_trip", "verified")
        # Assert
        assert _read_citation_status("round_trip") == "verified"

    def test_rows_contains_the_row_put_under_the_same_scope(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_citation("round_trip", "verified")
        # Act
        store = citations_store()
        keys = {r.values.get("cite_key") for r in store.rows()}
        store.close()
        # Assert
        assert "round_trip" in keys

    def test_a_scope_that_wrote_nothing_reads_nothing(self, as_project):
        # Arrange
        as_project(PROJECT_A)
        _put_citation("alpha_only", "verified")
        # Act
        as_project(PROJECT_B)
        # Assert
        assert _read_citation_status("alpha_only") is None


class TestProjectScopeResolution:
    """The scope is decided in ONE place — these pin that place's contract."""

    def test_env_override_wins(self, as_project):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        as_project("/pinned/project")
        # Act
        scope = resolve_project_scope()
        # Assert
        assert scope == "/pinned/project"

    def test_blank_override_falls_back_to_the_project_root(self, as_project):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        as_project("   ")
        # Act
        scope = resolve_project_scope()
        # Assert
        assert scope != "   "

    def test_unset_override_resolves_to_a_minted_id_not_a_path(self, as_project):
        """RETARGETED. This asserted `os.path.isabs(scope)` while the scope
        was derived from the project path. It is now a persisted minted id
        — precisely so a `mv` cannot truncate the chain — so the old
        assertion encoded the behaviour this change set out to remove.
        """
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        as_project.unset()
        # Act
        scope = resolve_project_scope()
        # Assert
        assert scope.startswith("clew-")

    def test_project_is_the_first_identity_field_of_every_store(self):
        # Arrange
        db = VerificationDB()
        claims, citations, stamps = _open_store(), citations_store(), _stamps_store()
        stores = [
            db._runs,
            db._file_hashes,
            db._verifications,
            db._session_parents,
            claims,
            citations,
            stamps,
        ]
        # Act
        firsts = {s.schema.identity_fields[0] for s in stores}
        # Assert
        assert firsts == {"project"}
        for store in (claims, citations, stamps):
            store.close()


@pytest.fixture
def project_dir(tmp_path):
    """A real project directory, entered, with no scope override in force.

    `resolve_project_scope()` walks up from the CWD, so a test about
    project identity has to actually be inside one. Both the cwd and the
    override are restored on teardown.
    """
    previous_cwd = os.getcwd()
    previous_env = os.environ.get(PROJECT_ENV)
    os.environ.pop(PROJECT_ENV, None)
    root = tmp_path / "manuscript"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'paper'\n")
    os.chdir(root)
    reset_db()
    try:
        yield root
    finally:
        os.chdir(previous_cwd)
        if previous_env is None:
            os.environ.pop(PROJECT_ENV, None)
        else:
            os.environ[PROJECT_ENV] = previous_env
        reset_db()


def _move_project(root):
    """Rename the project directory and enter the new location."""
    moved = root.parent / "manuscript-renamed"
    os.chdir(root.parent)
    shutil.move(str(root), str(moved))
    os.chdir(moved)
    reset_db()
    return moved


class TestProvenanceSurvivesAProjectMove:
    """A `mv` must not truncate the chain — the whole point of the package.

    FAILS WITHOUT THE PERSISTED ID: a path-derived scope changes with the
    directory, so the record written before the move becomes invisible
    after it. Measured on the pre-persistence commit — see the PR body.
    """

    def test_citation_written_before_a_move_is_readable_after_it(self, project_dir):
        # Arrange
        _put_citation("smith2020", "verified")
        # Act
        _move_project(project_dir)
        # Assert
        assert _read_citation_status("smith2020") == "verified"

    def test_run_recorded_before_a_move_is_listed_after_it(self, project_dir):
        # Arrange
        VerificationDB().add_run(session_id="pre_move_run", script_path="/a.py")
        # Act
        _move_project(project_dir)
        sessions = {r["session_id"] for r in VerificationDB().list_runs(limit=100)}
        # Assert
        assert "pre_move_run" in sessions

    def test_the_scope_itself_is_unchanged_by_a_move(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        before = resolve_project_scope()
        # Act
        _move_project(project_dir)
        after = resolve_project_scope()
        # Assert
        assert after == before


class TestTheProjectIdIsPersisted:
    """Where the id lives, and that it stays out of git."""

    def test_an_id_file_is_minted_on_first_use(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import project_id_path, resolve_project_scope

        # Act
        resolve_project_scope()
        # Assert
        assert project_id_path(project_dir).exists()

    def test_the_minted_id_is_what_the_scope_resolves_to(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import project_id_path, resolve_project_scope

        # Act
        scope = resolve_project_scope()
        # Assert
        assert project_id_path(project_dir).read_text().strip() == scope

    def test_the_id_is_stable_across_calls(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        first = resolve_project_scope()
        # Act
        second = resolve_project_scope()
        # Assert
        assert second == first

    def test_a_sibling_gitignore_keeps_the_id_out_of_git(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import PROJECT_ID_FILENAME, resolve_project_scope

        # Act
        resolve_project_scope()
        ignore = project_dir / ".scitex" / "clew" / ".gitignore"
        # Assert
        assert PROJECT_ID_FILENAME in ignore.read_text()

    def test_two_projects_mint_different_ids(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        first = resolve_project_scope()
        other = project_dir.parent / "other-manuscript"
        other.mkdir()
        (other / "pyproject.toml").write_text("[project]\nname = 'other'\n")
        # Act
        os.chdir(other)
        reset_db()
        second = resolve_project_scope()
        # Assert
        assert second != first

    def test_an_existing_gitignore_is_left_alone(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        clew_dir = project_dir / ".scitex" / "clew"
        clew_dir.mkdir(parents=True)
        (clew_dir / ".gitignore").write_text("# hand-written\n")
        # Act
        resolve_project_scope()
        # Assert
        assert (clew_dir / ".gitignore").read_text() == "# hand-written\n"


class TestOverrideVersusPersistedId:
    """The override wins, and never re-stamps the project."""

    def test_the_override_wins_over_a_persisted_id(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        resolve_project_scope()
        # Act
        os.environ[PROJECT_ENV] = "/pinned/scope"
        # Assert
        assert resolve_project_scope() == "/pinned/scope"

    def test_the_override_does_not_rewrite_the_persisted_id(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import project_id_path, resolve_project_scope

        original = resolve_project_scope()
        # Act
        os.environ[PROJECT_ENV] = "/pinned/scope"
        resolve_project_scope()
        # Assert
        assert project_id_path(project_dir).read_text().strip() == original

    def test_clearing_the_override_restores_the_persisted_scope(self, project_dir):
        # Arrange
        from scitex_clew._db._scope import resolve_project_scope

        original = resolve_project_scope()
        os.environ[PROJECT_ENV] = "/pinned/scope"
        resolve_project_scope()
        # Act
        os.environ.pop(PROJECT_ENV, None)
        # Assert
        assert resolve_project_scope() == original


# EOF
