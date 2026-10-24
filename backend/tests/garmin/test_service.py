"""Tests for unlinking and the sessions of a linked Garmin Connect account."""

from unittest.mock import MagicMock, patch

import garminconnect
import pytest

import core.exceptions as core_exceptions
import modules.garmin.service as garmin_service


class TestFetchUserIntegrationsAndValidateToken:
    def test_a_user_without_integrations_is_not_found(self):
        with (
            patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            garmin_service.get_linked_user_integrations(1, MagicMock())

    def test_an_unlinked_user_has_no_integrations_to_use(self):
        unlinked = MagicMock(garminconnect_token=None)
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=unlinked):
            assert garmin_service.get_linked_user_integrations(1, MagicMock()) is None

    def test_a_linked_user_is_returned(self):
        linked = MagicMock(garminconnect_token={"di_token": "enc"})
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=linked):
            assert garmin_service.get_linked_user_integrations(1, MagicMock()) is linked


class TestUnlinkExpiredAccount:
    def test_the_rejected_token_is_unlinked_and_the_user_told_in_one_commit(self):
        db = MagicMock()
        with (
            patch.object(
                garmin_service.user_integrations_integration, "unlink_garminconnect_account_if_token", return_value=True
            ) as unlink,
            patch.object(
                garmin_service.notifications_integration,
                "create_garmin_token_expired_notification",
                return_value=("n", "ws"),
            ),
            patch.object(garmin_service.notifications_integration, "push_notification") as push,
        ):
            garmin_service.unlink_expired_account(1, {"di_token": "old"}, db)

        unlink.assert_called_once_with(1, {"di_token": "old"}, db)
        db.commit.assert_called_once()
        push.assert_called_once_with(1, "n", "ws")

    def test_a_token_linked_since_is_left_alone_and_nobody_is_notified(self):
        db = MagicMock()
        with (
            patch.object(
                garmin_service.user_integrations_integration,
                "unlink_garminconnect_account_if_token",
                return_value=False,
            ),
            patch.object(garmin_service.notifications_integration, "create_garmin_token_expired_notification") as note,
            patch.object(garmin_service.notifications_integration, "push_notification") as push,
        ):
            garmin_service.unlink_expired_account(1, {"di_token": "old"}, db)

        db.commit.assert_not_called()
        note.assert_not_called()
        push.assert_not_called()


class TestSaveRefreshedToken:
    def _session(self):
        return garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})

    def test_a_refreshed_token_is_stored_while_the_old_one_is_still_linked(self):
        session = self._session()
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value={"di_token": "new"}),
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
            patch.object(
                garmin_service.user_integrations_integration, "replace_garminconnect_token_if_token", return_value=True
            ) as replace,
        ):
            garmin_service.save_refreshed_token(1, session)

        db = session_local.return_value.__enter__.return_value
        replace.assert_called_once_with(1, {"di_token": "enc"}, {"di_token": "new"}, db)
        db.commit.assert_called_once()

    def test_an_unchanged_token_writes_nothing(self):
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value=None),
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
        ):
            garmin_service.save_refreshed_token(1, self._session())

        session_local.assert_not_called()

    def test_a_token_linked_since_is_not_overwritten(self):
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value={"di_token": "new"}),
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
            patch.object(
                garmin_service.user_integrations_integration, "replace_garminconnect_token_if_token", return_value=False
            ),
        ):
            garmin_service.save_refreshed_token(1, self._session())

        session_local.return_value.__enter__.return_value.commit.assert_not_called()


def test_a_rejected_token_unlinks_the_account_it_was_stored_as():
    session = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
    with (
        patch.object(garmin_service.core_database, "SessionLocal") as session_local,
        patch.object(garmin_service, "unlink_expired_account") as unlink,
    ):
        garmin_service.handle_rejected_token(1, session, garminconnect.GarminConnectAuthenticationError("401"))

    unlink.assert_called_once_with(1, {"di_token": "enc"}, session_local.return_value.__enter__.return_value)


class TestUndecryptableToken:
    """A key that cannot read the stored token says nothing about the token: the account stays linked."""

    def test_a_sync_fails_and_the_account_stays_linked(self):
        with (
            patch.object(garmin_service, "unlink_expired_account") as unlink,
            patch.object(
                garmin_service.user_integrations_integration,
                "get_user_integrations",
                return_value=MagicMock(garminconnect_token={"di_token": "enc"}),
            ),
            patch.object(
                garmin_service.garmin_token_utils,
                "login_garminconnect_using_tokens",
                side_effect=core_exceptions.UndecryptableError(),
            ),
            pytest.raises(core_exceptions.UndecryptableError),
        ):
            garmin_service.get_user_garminconnect_session(1, MagicMock())

        unlink.assert_not_called()

    def test_a_migration_gets_no_client_and_changes_nothing(self):
        with (
            patch.object(garmin_service, "unlink_expired_account") as unlink,
            patch.object(
                garmin_service.user_integrations_integration,
                "get_user_integrations",
                return_value=MagicMock(garminconnect_token={"di_token": "enc"}),
            ),
            patch.object(
                garmin_service.garmin_token_utils,
                "login_garminconnect_using_tokens",
                side_effect=core_exceptions.UndecryptableError(),
            ),
        ):
            client = garmin_service.get_user_garminconnect_client(1, MagicMock())

        assert client is None
        unlink.assert_not_called()


class TestLinkedSession:
    def test_an_unlinked_user_yields_no_session_and_stores_nothing(self):
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=None),
            patch.object(garmin_service, "save_refreshed_token") as save,
            garmin_service.linked_session(1) as session,
        ):
            assert session is None

        save.assert_not_called()

    def test_the_refreshed_token_is_stored_when_the_body_succeeds(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "save_refreshed_token") as save,
            garmin_service.linked_session(1) as session,
        ):
            assert session is linked

        save.assert_called_once_with(1, linked)

    def test_the_refreshed_token_is_stored_when_the_body_fails(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "save_refreshed_token") as save,
            pytest.raises(RuntimeError),
            garmin_service.linked_session(1),
        ):
            raise RuntimeError("boom")

        save.assert_called_once_with(1, linked)

    def test_no_database_session_is_open_while_the_body_runs(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "save_refreshed_token"),
            garmin_service.linked_session(1),
        ):
            session_local.return_value.__exit__.assert_called_once()
