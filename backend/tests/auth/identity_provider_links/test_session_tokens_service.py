"""Tests for finding the sign-ins of ended sessions and ending the sessions of an unlinked provider."""

from unittest.mock import patch

import pytest

import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_provider_links.service as identity_links_service
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def db():
    session = create_sqlite_session()
    for session_id, user_id, idp_id in (("s1", 7, 3), ("s2", 7, 3), ("s3", 7, 4), ("s4", 8, 3)):
        identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, None, None, session)
    session.commit()
    yield session
    session.close()


def _alive(*session_ids):
    return patch.object(
        identity_links_service.sessions_integration, "get_existing_session_ids", return_value=set(session_ids)
    )


class TestOrphanedSessionTokens:
    """A sign-in is an orphan once its Endurain session no longer exists."""

    def test_the_sign_ins_without_a_session_are_returned_with_the_windows_last_id(self, db):
        with _alive("s1", "s3"):
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(0, 10, db)

        assert [row.session_id for row in orphans] == ["s2", "s4"]
        assert last_id == max(row.id for row in orphans)

    def test_a_user_can_be_asked_about_alone(self, db):
        with _alive("s1"):
            orphans, _ = identity_links_integration.get_orphaned_idp_session_tokens_page(0, 10, db, user_id=7)

        assert [row.session_id for row in orphans] == ["s2", "s3"]

    def test_the_cursor_moves_past_a_window_whose_sessions_all_exist(self, db):
        with _alive("s1", "s2"):
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(0, 2, db)

        assert orphans == []
        assert last_id is not None
        with _alive("s1", "s2"):
            orphans, _ = identity_links_integration.get_orphaned_idp_session_tokens_page(last_id, 2, db)
        assert [row.session_id for row in orphans] == ["s3", "s4"]

    def test_the_end_of_the_table_has_no_last_id(self, db):
        with _alive():
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(10_000, 10, db)

        assert (orphans, last_id) == ([], None)


class TestEndIdpSessions:
    """Unlinking a provider ends the user's sessions that signed in through it, and only those."""

    def test_each_live_session_of_that_user_and_provider_is_ended_through_the_sessions_surface(self, db):
        with (
            _alive("s1"),
            patch.object(identity_links_service.sessions_integration, "delete_session") as delete_session,
        ):
            ended = identity_links_integration.end_idp_sessions(7, 3, db)

        assert ended == 1
        delete_session.assert_called_once_with("s1", 7, db)

    def test_a_user_with_no_sign_in_through_the_provider_ends_nothing(self, db):
        with (
            _alive(),
            patch.object(identity_links_service.sessions_integration, "delete_session") as delete_session,
        ):
            assert identity_links_integration.end_idp_sessions(9, 3, db) == 0

        delete_session.assert_not_called()

    def test_the_sign_ins_stay_so_their_tokens_can_be_revoked(self, db):
        with _alive("s1", "s2"), patch.object(identity_links_service.sessions_integration, "delete_session"):
            identity_links_integration.end_idp_sessions(7, 3, db)

        assert identity_links_crud.get_idp_session_token("s1", db) is not None
