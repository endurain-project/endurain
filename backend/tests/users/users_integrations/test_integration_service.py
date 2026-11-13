"""The integrations surface forwards to its CRUD."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session_factory, ensure_user


def test_garmin_operations_reach_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with (
        patch.object(crud, "link_garminconnect_account") as link,
        patch.object(crud, "unlink_garminconnect_account") as unlink,
        patch.object(crud, "unlink_garminconnect_account_if_token", return_value=True),
        patch.object(crud, "set_user_garminconnect_sync_gear") as sync_gear,
        patch.object(crud, "list_user_ids_with_garminconnect_linked", return_value=[OTHER_USER_ID]) as linked,
    ):
        user_integrations_integration.link_garminconnect_account(MOCK_USER_ID, {"di_token": "enc"}, db)
        user_integrations_integration.unlink_garminconnect_account(MOCK_USER_ID, db)
        assert (
            user_integrations_integration.unlink_garminconnect_account_if_token(MOCK_USER_ID, {"di_token": "enc"}, db)
            is True
        )
        user_integrations_integration.set_garminconnect_sync_gear(MOCK_USER_ID, True, db)
        ids = user_integrations_integration.list_user_ids_with_garminconnect_linked(None, 10, db)

    link.assert_called_once_with(MOCK_USER_ID, {"di_token": "enc"}, db)
    unlink.assert_called_once_with(MOCK_USER_ID, db)
    sync_gear.assert_called_once_with(MOCK_USER_ID, True, db)
    linked.assert_called_once_with(None, 10, db)
    assert ids == [OTHER_USER_ID]


def test_strava_operations_reach_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with (
        patch.object(crud, "link_strava_account") as link,
        patch.object(crud, "unlink_strava_account") as unlink,
        patch.object(crud, "set_user_strava_client") as client,
        patch.object(crud, "set_user_strava_sync_gear") as sync_gear,
        patch.object(crud, "list_user_ids_with_strava_linked", return_value=[OTHER_USER_ID]) as linked,
    ):
        user_integrations_integration.link_strava_account(MOCK_USER_ID, {"access_token": "a"}, db)
        user_integrations_integration.unlink_strava_account(MOCK_USER_ID, db)
        user_integrations_integration.set_strava_client(MOCK_USER_ID, "id", "secret", db, if_match='"2"')
        user_integrations_integration.set_strava_sync_gear(MOCK_USER_ID, True, db)
        ids = user_integrations_integration.list_user_ids_with_strava_linked(None, 10, db)

    link.assert_called_once_with(MOCK_USER_ID, {"access_token": "a"}, db)
    unlink.assert_called_once_with(MOCK_USER_ID, db)
    client.assert_called_once_with(MOCK_USER_ID, "id", "secret", db, if_match='"2"')
    sync_gear.assert_called_once_with(MOCK_USER_ID, True, db)
    linked.assert_called_once_with(None, 10, db)
    assert ids == [OTHER_USER_ID]


def test_strava_token_unlink_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with patch.object(crud, "unlink_strava_tokens_if_refresh_token", return_value=True) as unlink:
        assert user_integrations_integration.unlink_strava_tokens_if_refresh_token(MOCK_USER_ID, "enc", db) is True

    unlink.assert_called_once_with(MOCK_USER_ID, "enc", db, revoked_at=None)


def test_strava_revocation_time_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    revoked_at = datetime(2026, 11, 5, tzinfo=UTC)
    with patch.object(crud, "unlink_strava_tokens_if_refresh_token", return_value=True) as unlink:
        user_integrations_integration.unlink_strava_tokens_if_refresh_token(
            MOCK_USER_ID, "enc", db, revoked_at=revoked_at
        )

    unlink.assert_called_once_with(MOCK_USER_ID, "enc", db, revoked_at=revoked_at)


def test_strava_token_replacement_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with patch.object(crud, "replace_strava_tokens_if_refresh_token", return_value=True) as replace:
        assert (
            user_integrations_integration.replace_strava_tokens_if_refresh_token(MOCK_USER_ID, "enc", {"k": 1}, db)
            is True
        )

    replace.assert_called_once_with(MOCK_USER_ID, "enc", {"k": 1}, db)


class TestRequireUserIntegrations:
    """A user's integrations are returned, and their absence is refused."""

    @pytest.fixture
    def session_factory(self):
        factory = create_sqlite_session_factory()
        ensure_user(factory, MOCK_USER_ID)
        yield factory
        factory.kw["bind"].dispose()

    def test_the_users_integrations_are_returned(self, session_factory):
        with session_factory() as db:
            user_integrations_integration.create_integrations(MOCK_USER_ID, db)
            db.commit()

            assert user_integrations_integration.require_user_integrations(MOCK_USER_ID, db).user_id == MOCK_USER_ID

    def test_a_user_without_integrations_is_refused(self, session_factory):
        with session_factory() as db, pytest.raises(core_exceptions.NotFoundError):
            user_integrations_integration.require_user_integrations(MOCK_USER_ID, db)
