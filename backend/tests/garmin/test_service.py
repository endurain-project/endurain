"""Tests for unlinking and the sessions of a linked Garmin Connect account."""

from unittest.mock import MagicMock, patch

import garminconnect
import pytest
import sqlalchemy.exc

import core.exceptions as core_exceptions
import modules.garmin.service as garmin_service
from tests._helpers import garmin as garmin_helpers
from tests._helpers.auth import MOCK_USER_ID


class TestFetchUserIntegrationsAndValidateToken:
    def test_a_user_without_integrations_is_not_found(self):
        with (
            patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            garmin_service.get_linked_user_integrations(MOCK_USER_ID, MagicMock())

    def test_an_unlinked_user_has_no_integrations_to_use(self):
        unlinked = MagicMock(garminconnect_token=None)
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=unlinked):
            assert garmin_service.get_linked_user_integrations(MOCK_USER_ID, MagicMock()) is None

    def test_a_linked_user_is_returned(self):
        linked = MagicMock(garminconnect_token={"di_token": "enc"})
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=linked):
            assert garmin_service.get_linked_user_integrations(MOCK_USER_ID, MagicMock()) is linked


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
            garmin_service.unlink_expired_account(MOCK_USER_ID, {"di_token": "old"}, db)

        unlink.assert_called_once_with(MOCK_USER_ID, {"di_token": "old"}, db)
        db.commit.assert_called_once()
        push.assert_called_once_with(MOCK_USER_ID, "n", "ws")

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
            garmin_service.unlink_expired_account(MOCK_USER_ID, {"di_token": "old"}, db)

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
            garmin_service.save_refreshed_token(MOCK_USER_ID, session)

        db = session_local.return_value.__enter__.return_value
        replace.assert_called_once_with(MOCK_USER_ID, {"di_token": "enc"}, {"di_token": "new"}, db)
        db.commit.assert_called_once()

    def test_an_unchanged_token_writes_nothing(self):
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value=None),
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
        ):
            garmin_service.save_refreshed_token(MOCK_USER_ID, self._session())

        session_local.assert_not_called()

    def test_a_token_linked_since_is_not_overwritten(self):
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value={"di_token": "new"}),
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
            patch.object(
                garmin_service.user_integrations_integration, "replace_garminconnect_token_if_token", return_value=False
            ),
        ):
            garmin_service.save_refreshed_token(MOCK_USER_ID, self._session())

        session_local.return_value.__enter__.return_value.commit.assert_not_called()


class TestSaveRefreshedTokenFailures:
    def _save(self, error):
        session = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.garmin_token_utils, "refreshed_token", return_value={"di_token": "new"}),
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(
                garmin_service.user_integrations_integration, "replace_garminconnect_token_if_token", side_effect=error
            ),
        ):
            garmin_service.save_refreshed_token(MOCK_USER_ID, session)

    @pytest.mark.parametrize(
        "error", [sqlalchemy.exc.OperationalError("s", {}, Exception("db")), core_exceptions.CryptographyError()]
    )
    def test_a_storage_failure_is_logged_not_raised(self, error):
        self._save(error)

    def test_a_bug_is_not_swallowed(self):
        with pytest.raises(RuntimeError):
            self._save(RuntimeError("bug"))


def test_a_rejected_token_unlinks_the_account_it_was_stored_as():
    session = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
    with (
        patch.object(garmin_service.core_database, "SessionLocal") as session_local,
        patch.object(garmin_service, "unlink_expired_account") as unlink,
    ):
        garmin_service.handle_rejected_token(
            MOCK_USER_ID, session, garminconnect.GarminConnectAuthenticationError("401")
        )

    unlink.assert_called_once_with(MOCK_USER_ID, {"di_token": "enc"}, session_local.return_value.__enter__.return_value)


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
            garmin_service.get_user_garminconnect_session(MOCK_USER_ID, MagicMock())

        unlink.assert_not_called()

    def test_a_user_without_integrations_is_simply_not_linked(self, caplog):
        """The same "not linked" event Strava reports, at the same level."""
        with (
            patch.object(
                garmin_service, "get_linked_user_integrations", side_effect=core_exceptions.NotFoundError("missing")
            ),
            caplog.at_level("DEBUG", logger=garmin_service.logger.name),
        ):
            assert garmin_service.get_user_garminconnect_session(MOCK_USER_ID, MagicMock()) is None

        assert {record.levelname for record in caplog.records} == {"DEBUG"}


class TestLinkedSession:
    def test_an_unlinked_user_yields_no_session_and_stores_nothing(self):
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=None),
            patch.object(garmin_service, "save_refreshed_token") as save,
            garmin_service.linked_session(MOCK_USER_ID, garmin_helpers.rate_limits()) as session,
        ):
            assert session is None

        save.assert_not_called()

    def test_the_refreshed_token_is_stored_when_the_body_succeeds(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "fresh_session", side_effect=lambda _user, restored, _claims: restored),
            patch.object(garmin_service, "save_refreshed_token") as save,
            garmin_service.linked_session(MOCK_USER_ID, garmin_helpers.rate_limits()) as session,
        ):
            assert session is linked

        save.assert_called_once_with(MOCK_USER_ID, linked)

    def test_the_refreshed_token_is_stored_when_the_body_fails(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "save_refreshed_token") as save,
            pytest.raises(RuntimeError),
            garmin_service.linked_session(MOCK_USER_ID, garmin_helpers.rate_limits()),
        ):
            raise RuntimeError("boom")

        save.assert_called_once_with(MOCK_USER_ID, linked)

    def test_no_database_session_is_open_while_the_body_runs(self):
        linked = garmin_service.GarminSession(MagicMock(), {"di_token": "enc"})
        with (
            patch.object(garmin_service.core_database, "SessionLocal") as session_local,
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=linked),
            patch.object(garmin_service, "save_refreshed_token"),
            garmin_service.linked_session(MOCK_USER_ID, garmin_helpers.rate_limits()),
        ):
            session_local.return_value.__exit__.assert_called_once()


class TestRateLimit:
    """A Garmin Connect 429 is remembered for every process, and refuses the calls that follow."""

    def test_a_rate_limit_is_recorded_and_its_clearing_time_returned(self):
        rate_limits = garmin_helpers.rate_limits()

        error = garmin_service.rate_limit_error(RuntimeError("429"), MOCK_USER_ID, rate_limits)

        assert isinstance(error, core_exceptions.TooManyRequestsError)
        assert error.retry_at == rate_limits.rate_limited_until(MOCK_USER_ID)
        assert error.scope == core_exceptions.TooManyRequestsScope.PROVIDER

    def test_a_call_is_refused_while_the_account_is_limited(self):
        rate_limits = garmin_helpers.rate_limits()
        until = rate_limits.mark_rate_limited(MOCK_USER_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            garmin_service.raise_if_rate_limited(MOCK_USER_ID, rate_limits)

        assert raised.value.retry_at == until
        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER

    def test_a_call_is_allowed_when_nothing_is_limited(self):
        garmin_service.raise_if_rate_limited(MOCK_USER_ID, garmin_helpers.rate_limits())

    def test_a_limited_account_gets_no_session_and_no_token_is_restored(self):
        rate_limits = garmin_helpers.rate_limits()
        rate_limits.mark_rate_limited(MOCK_USER_ID)

        with (
            patch.object(garmin_service, "get_user_garminconnect_session") as restore,
            pytest.raises(core_exceptions.TooManyRequestsError),
            garmin_service.linked_session(MOCK_USER_ID, rate_limits),
        ):
            pass

        restore.assert_not_called()


class TestRefreshSerialisation:
    """Two syncs of one user never refresh the Garmin Connect token at once, and a refreshed token is kept."""

    @pytest.fixture(autouse=True)
    def _no_waiting(self):
        with patch.object(garmin_service.time, "sleep"):
            yield

    def _session(self, label: str = "old"):
        return garmin_service.GarminSession(MagicMock(), {"di_token": label})

    def test_a_live_token_is_used_without_a_claim(self):
        session = self._session()
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=False),
            patch.object(garmin_service.garmin_token_utils, "refresh") as refresh,
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, session, claims) is session

        refresh.assert_not_called()
        assert claims.claim_token_refresh(MOCK_USER_ID)

    def test_an_expiring_token_is_refreshed_stored_and_the_claim_released(self):
        stored = self._session()
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=stored),
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=True),
            patch.object(garmin_service.garmin_token_utils, "refresh") as refresh,
            patch.object(garmin_service, "save_refreshed_token") as save,
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims) is stored

        refresh.assert_called_once_with(stored.client.client)
        save.assert_called_once_with(MOCK_USER_ID, stored)
        assert claims.claim_token_refresh(MOCK_USER_ID)

    def test_a_token_another_process_refreshed_is_used_without_refreshing_again(self):
        reread = self._session("new")
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=reread),
            patch.object(
                garmin_service.garmin_token_utils,
                "expires_soon",
                side_effect=lambda client: client is not reread.client.client,
            ),
            patch.object(garmin_service.garmin_token_utils, "refresh") as refresh,
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims) is reread

        refresh.assert_not_called()

    def test_a_held_claim_makes_the_caller_wait_and_use_the_refreshed_token(self):
        reread = self._session("new")
        claims = garmin_helpers.rate_limits()
        assert claims.claim_token_refresh(MOCK_USER_ID)

        def holder_finishes(_seconds):
            claims.release_token_refresh(MOCK_USER_ID)

        with (
            patch.object(garmin_service.time, "sleep", side_effect=holder_finishes) as sleep,
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=reread),
            patch.object(
                garmin_service.garmin_token_utils,
                "expires_soon",
                side_effect=lambda client: client is not reread.client.client,
            ),
            patch.object(garmin_service.garmin_token_utils, "refresh") as refresh,
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims) is reread

        sleep.assert_called_once()
        refresh.assert_not_called()

    def test_a_claim_held_past_the_wait_defers_the_sync(self):
        claims = garmin_helpers.rate_limits()
        assert claims.claim_token_refresh(MOCK_USER_ID)
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=self._session()),
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=True),
            patch.object(garmin_service.garmin_token_utils, "refresh") as refresh,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims)

        refresh.assert_not_called()

    def test_the_claim_is_released_when_the_refresh_raises(self):
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=self._session()),
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=True),
            patch.object(garmin_service.garmin_token_utils, "refresh", side_effect=RuntimeError("network")),
            pytest.raises(RuntimeError),
        ):
            garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims)

        assert claims.claim_token_refresh(MOCK_USER_ID)

    def test_a_refused_refresh_leaves_the_session_to_the_library_and_releases_the_claim(self):
        stored = self._session()
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=stored),
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=True),
            patch.object(
                garmin_service.garmin_token_utils,
                "refresh",
                side_effect=garminconnect.GarminConnectAuthenticationError("refused"),
            ),
            patch.object(garmin_service, "save_refreshed_token") as save,
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims) is stored

        save.assert_not_called()
        assert claims.claim_token_refresh(MOCK_USER_ID)

    def test_a_user_unlinked_meanwhile_gets_no_session(self):
        claims = garmin_helpers.rate_limits()
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=None),
            patch.object(garmin_service.garmin_token_utils, "expires_soon", return_value=True),
        ):
            assert garmin_service.fresh_session(MOCK_USER_ID, self._session(), claims) is None

    def test_linked_session_refreshes_before_the_body_runs(self):
        restored = self._session()
        fresh = self._session("new")
        with (
            patch.object(garmin_service.core_database, "SessionLocal"),
            patch.object(garmin_service, "get_user_garminconnect_session", return_value=restored),
            patch.object(garmin_service, "fresh_session", return_value=fresh) as fresh_session,
            patch.object(garmin_service, "save_refreshed_token") as save,
            garmin_service.linked_session(MOCK_USER_ID, garmin_helpers.rate_limits()) as session,
        ):
            assert session is fresh

        fresh_session.assert_called_once()
        save.assert_called_once_with(MOCK_USER_ID, fresh)
