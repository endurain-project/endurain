"""Strava account linking: the state is single-use and the caller's, and a failed exchange keeps the setup."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service


@pytest.fixture
def oauth_states():
    return strava_oauth_state_store.StravaOAuthStateStore(platform_runtime.get_state())


def _link(oauth_states, *, user_id=1, stored_state="s", sent_state="s", has_credentials=True, exchange_error=None):
    if stored_state is not None:
        oauth_states.begin(1, stored_state)
    integrations = SimpleNamespace(
        strava_client_id="id" if has_credentials else None,
        strava_client_secret="stored" if has_credentials else None,
    )
    client = MagicMock()
    if exchange_error:
        client.exchange_code_for_token.side_effect = exchange_error
    db = MagicMock()
    with (
        patch.object(strava_service, "SessionLocal"),
        patch.object(strava_service.user_integrations_integration, "get_user_integrations", return_value=integrations),
        patch.object(strava_service.user_integrations_integration, "link_strava_account") as link,
        patch.object(strava_service.user_integrations_integration, "unlink_strava_account") as unlink,
        patch.object(strava_service.strava_client_service, "create_strava_client", return_value=client),
        patch.object(strava_service.core_cryptography, "decrypt_token_fernet", return_value="x"),
    ):
        error = None
        result = None
        try:
            result = strava_service.link_account(
                strava_schema.StravaLinkRequest(state=sent_state, code="c"), user_id, oauth_states, db
            )
        except core_exceptions.DomainError as exc:
            error = exc
        return link, unlink, db, result, error


class TestLinkAccount:
    def test_the_owner_can_link(self, oauth_states):
        link, unlink, db, result, error = _link(oauth_states)

        assert error is None
        assert result.detail == "Strava linked successfully for user 1"
        link.assert_called_once()
        unlink.assert_not_called()
        db.commit.assert_called_once()

    def test_a_state_is_good_for_one_link_only(self, oauth_states):
        _link(oauth_states)
        link, _unlink, _db, _result, error = _link(oauth_states, stored_state=None)

        assert isinstance(error, core_exceptions.InvalidInputError)
        link.assert_not_called()

    def test_another_users_stored_state_is_never_consulted(self, oauth_states):
        """The state is held per user, so user 2 cannot redeem the one user 1 stored."""
        link, _unlink, _db, _result, error = _link(oauth_states, user_id=2)

        assert isinstance(error, core_exceptions.InvalidInputError)
        link.assert_not_called()

    def test_a_wrong_state_is_refused_and_uses_up_the_stored_one(self, oauth_states):
        link, _unlink, _db, _result, error = _link(oauth_states, sent_state="forged")

        assert isinstance(error, core_exceptions.InvalidInputError)
        link.assert_not_called()
        assert oauth_states.consume(1, "s") is False

    def test_a_user_without_client_credentials_is_refused(self, oauth_states):
        link, _unlink, _db, _result, error = _link(oauth_states, has_credentials=False)

        assert isinstance(error, core_exceptions.InvalidInputError)
        link.assert_not_called()

    def test_a_failed_exchange_answers_424_without_leaking_the_cause_and_keeps_the_setup(self, oauth_states):
        link, unlink, db, _result, error = _link(oauth_states, exchange_error=RuntimeError("secret-token-123 rejected"))

        assert isinstance(error, core_exceptions.DependencyFailedError)
        assert error.status_code == 424
        assert "secret-token-123" not in error.detail
        link.assert_not_called()
        unlink.assert_not_called()
        db.commit.assert_not_called()


class TestStoredCredentials:
    def test_the_client_is_stored_and_committed(self):
        db = MagicMock()
        with patch.object(strava_service.user_integrations_integration, "set_strava_client") as store:
            strava_service.set_client(
                7, strava_schema.StravaClientCredentials(client_id=123, client_secret="secret"), db
            )

        store.assert_called_once_with(7, "123", "secret", db)
        db.commit.assert_called_once()


class TestOAuthState:
    def test_a_stored_state_is_consumed_once(self, oauth_states):
        strava_service.set_state(7, "abc", oauth_states)

        assert oauth_states.consume(7, "abc") is True
        assert oauth_states.consume(7, "abc") is False

    def test_a_cleared_state_can_no_longer_be_used(self, oauth_states):
        strava_service.set_state(7, "abc", oauth_states)
        strava_service.clear_state(7, oauth_states)

        assert oauth_states.consume(7, "abc") is False

    def test_a_new_state_replaces_the_old_one(self, oauth_states):
        strava_service.set_state(7, "old", oauth_states)
        strava_service.set_state(7, "new", oauth_states)

        assert oauth_states.consume(7, "old") is False


class TestRequestActivitiesSync:
    def test_a_range_ending_before_it_starts_is_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_service.request_activities_sync(1, date(2026, 2, 1), date(2026, 1, 1), MagicMock(), MagicMock())

    def test_the_whole_last_day_is_requested(self):
        with patch.object(
            strava_service.activity_ingestion_integration, "request_provider_sync", return_value="job"
        ) as request:
            job = strava_service.request_activities_sync(
                1, date(2026, 1, 1), date(2026, 1, 2), MagicMock(), MagicMock()
            )

        assert job == "job"
        _user, provider, start, end, *_ = request.call_args.args
        assert provider == "strava"
        assert (start.hour, end.hour, end.minute) == (0, 23, 59)


class TestUnlinkAccount:
    def _run(self, *, linked=True, deauthorize_error=None):
        client = MagicMock()
        if deauthorize_error:
            client.deauthorize.side_effect = deauthorize_error
        open_sessions = []
        sessions = MagicMock()
        sessions.return_value.__enter__.side_effect = lambda: open_sessions.append(1) or MagicMock()
        sessions.return_value.__exit__.side_effect = lambda *_e: open_sessions.pop() and False
        during_deauthorize = []
        client.deauthorize.side_effect = lambda: (
            during_deauthorize.append(len(open_sessions)),
            deauthorize_error and (_ for _ in ()).throw(deauthorize_error),
        )
        with (
            patch.object(strava_service, "SessionLocal", sessions),
            patch.object(
                strava_service.strava_client_service,
                "fetch_user_integrations_and_validate_token",
                return_value=object() if linked else None,
            ),
            patch.object(strava_service.strava_client_service, "create_strava_client", return_value=client),
            patch.object(strava_service.gears_integration, "delete_all_strava_gear_for_user") as delete_gear,
            patch.object(strava_service.activity_integration, "delete_all_strava_activities") as delete_activities,
            patch.object(strava_service.user_integrations_integration, "unlink_strava_account") as unlink,
        ):
            result = strava_service.unlink_account(7)
        return result, client, delete_gear, delete_activities, unlink, during_deauthorize

    def test_the_account_is_deauthorized_then_unlinked_and_imported_data_cleared(self):
        result, client, delete_gear, delete_activities, unlink, _ = self._run()

        assert result is True
        client.deauthorize.assert_called_once()
        delete_gear.assert_called_once()
        delete_activities.assert_called_once()
        unlink.assert_called_once()

    def test_a_refused_deauthorization_still_unlinks_and_clears_imported_data(self):
        result, _client, delete_gear, delete_activities, unlink, _ = self._run(
            deauthorize_error=RuntimeError("revoked already")
        )

        assert result is True
        delete_gear.assert_called_once()
        delete_activities.assert_called_once()
        unlink.assert_called_once()

    def test_strava_is_called_with_no_database_session_open(self):
        *_, during_deauthorize = self._run()

        assert during_deauthorize == [0]

    def test_an_account_that_is_not_linked_is_left_alone(self):
        result, client, delete_gear, delete_activities, unlink, _ = self._run(linked=False)

        assert result is False
        client.deauthorize.assert_not_called()
        delete_gear.assert_not_called()
        delete_activities.assert_not_called()
        unlink.assert_not_called()
