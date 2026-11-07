"""The integrations surface forwards to its CRUD."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._helpers.db import create_sqlite_session_factory, ensure_user


def test_garmin_operations_reach_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with (
        patch.object(crud, "link_garminconnect_account") as link,
        patch.object(crud, "unlink_garminconnect_account") as unlink,
        patch.object(crud, "unlink_garminconnect_account_if_token", return_value=True),
        patch.object(crud, "set_user_garminconnect_sync_gear") as sync_gear,
        patch.object(crud, "list_user_ids_with_garminconnect_linked", return_value=[3]) as linked,
    ):
        user_integrations_integration.link_garminconnect_account(1, {"di_token": "enc"}, db)
        user_integrations_integration.unlink_garminconnect_account(1, db)
        assert user_integrations_integration.unlink_garminconnect_account_if_token(1, {"di_token": "enc"}, db) is True
        user_integrations_integration.set_garminconnect_sync_gear(1, True, db)
        ids = user_integrations_integration.list_user_ids_with_garminconnect_linked(0, 10, db)

    link.assert_called_once_with(1, {"di_token": "enc"}, db)
    unlink.assert_called_once_with(1, db)
    sync_gear.assert_called_once_with(1, True, db)
    linked.assert_called_once_with(0, 10, db)
    assert ids == [3]


def test_strava_operations_reach_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with (
        patch.object(crud, "link_strava_account") as link,
        patch.object(crud, "unlink_strava_account") as unlink,
        patch.object(crud, "set_user_strava_client") as client,
        patch.object(crud, "set_user_strava_sync_gear") as sync_gear,
        patch.object(crud, "list_user_ids_with_strava_linked", return_value=[2]) as linked,
    ):
        user_integrations_integration.link_strava_account(1, {"access_token": "a"}, db)
        user_integrations_integration.unlink_strava_account(1, db)
        user_integrations_integration.set_strava_client(1, "id", "secret", db, if_match='"2"')
        user_integrations_integration.set_strava_sync_gear(1, True, db)
        ids = user_integrations_integration.list_user_ids_with_strava_linked(0, 10, db)

    link.assert_called_once_with(1, {"access_token": "a"}, db)
    unlink.assert_called_once_with(1, db)
    client.assert_called_once_with(1, "id", "secret", db, if_match='"2"')
    sync_gear.assert_called_once_with(1, True, db)
    linked.assert_called_once_with(0, 10, db)
    assert ids == [2]


def test_strava_token_unlink_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with patch.object(crud, "unlink_strava_tokens_if_refresh_token", return_value=True) as unlink:
        assert user_integrations_integration.unlink_strava_tokens_if_refresh_token(1, "enc", db) is True

    unlink.assert_called_once_with(1, "enc", db, revoked_at=None)


def test_strava_revocation_time_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    revoked_at = datetime(2026, 11, 5, tzinfo=UTC)
    with patch.object(crud, "unlink_strava_tokens_if_refresh_token", return_value=True) as unlink:
        user_integrations_integration.unlink_strava_tokens_if_refresh_token(1, "enc", db, revoked_at=revoked_at)

    unlink.assert_called_once_with(1, "enc", db, revoked_at=revoked_at)


def test_strava_token_replacement_reaches_the_crud():
    db = MagicMock()
    crud = user_integrations_integration.user_integrations_crud
    with patch.object(crud, "replace_strava_tokens_if_refresh_token", return_value=True) as replace:
        assert user_integrations_integration.replace_strava_tokens_if_refresh_token(1, "enc", {"k": 1}, db) is True

    replace.assert_called_once_with(1, "enc", {"k": 1}, db)


class TestRequireUserIntegrations:
    """A user's integrations are returned, and their absence is refused."""

    @pytest.fixture
    def session_factory(self):
        factory = create_sqlite_session_factory()
        ensure_user(factory, 1)
        yield factory
        factory.kw["bind"].dispose()

    def test_the_users_integrations_are_returned(self, session_factory):
        with session_factory() as db:
            user_integrations_integration.create_integrations(1, db)
            db.commit()

            assert user_integrations_integration.require_user_integrations(1, db).user_id == 1

    def test_a_user_without_integrations_is_refused(self, session_factory):
        with session_factory() as db, pytest.raises(core_exceptions.NotFoundError):
            user_integrations_integration.require_user_integrations(1, db)
