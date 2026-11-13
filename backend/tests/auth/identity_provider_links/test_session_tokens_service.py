"""Tests for finding the sign-ins of ended sessions and ending the sessions of an unlinked provider."""

import uuid
from unittest.mock import patch

import pytest

import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_provider_links.service as identity_links_service
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session

IDP_3 = uuid.uuid4()
IDP_4 = uuid.uuid4()
S1, S2, S3, S4 = (uuid.UUID(int=n) for n in range(1, 5))
A1, A2, A3, A4, A5, A6 = (uuid.UUID(int=n) for n in range(101, 107))


@pytest.fixture
def db():
    session = create_sqlite_session()
    for session_id, user_id, idp_id in (
        (S1, MOCK_USER_ID, IDP_3),
        (S2, MOCK_USER_ID, IDP_3),
        (S3, MOCK_USER_ID, IDP_4),
        (S4, OTHER_USER_ID, IDP_3),
    ):
        identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, None, None, session)
    session.commit()
    yield session
    session.close()


def _in_id_order(db, *session_ids):
    """The given sessions in the order the keyset walks them: by ascending random id."""
    walked = [row.session_id for row in identity_links_crud.get_idp_session_tokens_page(None, 100, db)]
    return [session_id for session_id in walked if session_id in session_ids]


def _alive(*session_ids):
    return patch.object(
        identity_links_service.sessions_integration, "get_existing_session_ids", return_value=set(session_ids)
    )


def _live(*session_ids):
    """Patch the sessions surface so only the given sessions exist to be ended; the mock records each attempt."""
    return patch.object(
        identity_links_service.sessions_integration,
        "delete_session_if_present",
        side_effect=lambda session_id, user_id, db: session_id in session_ids,
    )


class TestOrphanedSessionTokens:
    """A sign-in is an orphan once its Endurain session no longer exists."""

    def test_the_sign_ins_without_a_session_are_returned_with_the_windows_last_id(self, db):
        with _alive(S1, S3):
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(None, 10, db)

        assert [row.session_id for row in orphans] == _in_id_order(db, S2, S4)
        assert last_id == identity_links_crud.get_idp_session_tokens_page(None, 10, db)[-1].id

    def test_a_user_can_be_asked_about_alone(self, db):
        with _alive(S1):
            orphans, _ = identity_links_integration.get_orphaned_idp_session_tokens_page(
                None, 10, db, user_id=MOCK_USER_ID
            )

        assert [row.session_id for row in orphans] == _in_id_order(db, S2, S3)

    def test_the_cursor_moves_past_a_window_whose_sessions_all_exist(self, db):
        first_window = _in_id_order(db, S1, S2, S3, S4)[:2]
        with _alive(*first_window):
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(None, 2, db)

        assert orphans == []
        assert last_id is not None
        with _alive(*first_window):
            orphans, _ = identity_links_integration.get_orphaned_idp_session_tokens_page(last_id, 2, db)
        assert [row.session_id for row in orphans] == _in_id_order(db, S1, S2, S3, S4)[2:]

    def test_the_end_of_the_table_has_no_last_id(self, db):
        with _alive():
            orphans, last_id = identity_links_integration.get_orphaned_idp_session_tokens_page(
                uuid.UUID(int=2**128 - 1), 10, db
            )

        assert (orphans, last_id) == ([], None)


class TestEndIdpSessions:
    """Unlinking a provider ends the user's sessions that signed in through it, and only those."""

    def test_each_live_session_of_that_user_and_provider_is_ended_through_the_sessions_surface(self, db):
        with (
            _live(S1) as delete_session,
        ):
            ended = identity_links_integration.end_idp_sessions(MOCK_USER_ID, IDP_3, db)

        assert ended == 1
        assert [call.args for call in delete_session.call_args_list] == [
            (S1, MOCK_USER_ID, db),
            (S2, MOCK_USER_ID, db),
        ]

    def test_a_session_that_vanishes_before_it_is_ended_is_skipped_and_not_counted(self, db):
        with _live(S2) as delete_session:
            ended = identity_links_integration.end_idp_sessions(MOCK_USER_ID, IDP_3, db)

        assert ended == 1
        assert [call.args[0] for call in delete_session.call_args_list] == [S1, S2]

    def test_a_user_with_no_sign_in_through_the_provider_ends_nothing(self, db):
        with (
            _live() as delete_session,
        ):
            assert identity_links_integration.end_idp_sessions(uuid.uuid4(), IDP_3, db) == 0

        delete_session.assert_not_called()

    def test_the_sign_ins_stay_so_their_tokens_can_be_revoked(self, db):
        with _live(S1, S2):
            identity_links_integration.end_idp_sessions(MOCK_USER_ID, IDP_3, db)

        assert identity_links_crud.get_idp_session_token(S1, db) is not None


class TestEndAllIdpSessions:
    """Disabling a provider ends every session it signed in, whoever the user, and no other provider's."""

    def test_each_live_session_of_the_provider_is_ended_for_its_owner(self, db):
        with _live(S1, S4) as delete_session:
            ended = identity_links_integration.end_all_idp_sessions(IDP_3, db)

        assert ended == 2
        assert sorted(call.args[:2] for call in delete_session.call_args_list) == [
            (S1, MOCK_USER_ID),
            (S2, MOCK_USER_ID),
            (S4, OTHER_USER_ID),
        ]

    def test_a_provider_with_no_sign_in_ends_nothing(self, db):
        with _live() as delete_session:
            assert identity_links_integration.end_all_idp_sessions(uuid.uuid4(), db) == 0

        delete_session.assert_not_called()


class TestEndIdpSessionsBySid:
    """A back-channel logout that names a provider session ends the sessions signed in under it."""

    @pytest.fixture
    def sid_db(self):
        session = create_sqlite_session()
        for session_id, user_id, idp_id, sid in (
            (A1, MOCK_USER_ID, IDP_3, "sid-1"),
            (A2, MOCK_USER_ID, IDP_3, "sid-1"),
            (A3, OTHER_USER_ID, IDP_3, "sid-1"),
            (A4, MOCK_USER_ID, IDP_3, "sid-2"),
            (A5, MOCK_USER_ID, IDP_4, "sid-1"),
            (A6, MOCK_USER_ID, IDP_3, None),
        ):
            identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, None, None, session, idp_sid=sid)
        session.commit()
        yield session
        session.close()

    def test_the_live_sessions_of_that_provider_session_end_counted_per_user(self, sid_db):
        with (
            _live(A1, A3, A4, A5) as delete_session,
        ):
            ended = identity_links_integration.end_idp_sessions_by_sid(IDP_3, "sid-1", sid_db)

        assert ended == {MOCK_USER_ID: 1, OTHER_USER_ID: 1}
        assert sorted(call.args[:2] for call in delete_session.call_args_list) == [
            (A1, MOCK_USER_ID),
            (A2, MOCK_USER_ID),
            (A3, OTHER_USER_ID),
        ]

    def test_a_session_that_vanishes_is_skipped_and_the_others_still_end(self, sid_db):
        with _live(A1, A3) as delete_session:
            ended = identity_links_integration.end_idp_sessions_by_sid(IDP_3, "sid-1", sid_db)

        assert ended == {MOCK_USER_ID: 1, OTHER_USER_ID: 1}
        assert delete_session.call_count == 3

    def test_a_user_restricts_the_match_to_their_own_sessions(self, sid_db):
        with (
            _live(A1, A2, A3) as delete_session,
        ):
            ended = identity_links_integration.end_idp_sessions_by_sid(IDP_3, "sid-1", sid_db, user_id=OTHER_USER_ID)

        assert ended == {OTHER_USER_ID: 1}
        delete_session.assert_called_once_with(A3, OTHER_USER_ID, sid_db)

    def test_an_unknown_provider_session_ends_nothing(self, sid_db):
        with (
            _live(A1, A2) as delete_session,
        ):
            assert identity_links_integration.end_idp_sessions_by_sid(IDP_3, "sid-9", sid_db) == {}

        delete_session.assert_not_called()

    def test_the_sid_is_stored_with_the_sign_in(self, sid_db):
        assert identity_links_crud.get_idp_session_token(A1, sid_db).idp_sid == "sid-1"
        assert identity_links_crud.get_idp_session_token(A6, sid_db).idp_sid is None
