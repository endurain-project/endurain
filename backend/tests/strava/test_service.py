"""Strava account linking: the state belongs to the caller, and a failed exchange leaves nothing linked."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.strava.service as strava_service


def _link(user_id: int, owner_id: int = 1, *, has_credentials=True, exchange_error=None):
    credentials = {"strava_client_id": "id", "strava_client_secret": "stored"} if has_credentials else {}
    integrations = SimpleNamespace(
        user_id=owner_id,
        **{"strava_client_id": None, "strava_client_secret": None, **credentials},
    )
    client = MagicMock()
    if exchange_error:
        client.exchange_code_for_token.side_effect = exchange_error
    db = MagicMock()
    with (
        patch.object(
            strava_service.user_integrations_integration, "get_integrations_by_strava_state", return_value=integrations
        ),
        patch.object(strava_service.user_integrations_integration, "link_strava_account") as link,
        patch.object(strava_service.user_integrations_integration, "unlink_strava_account") as unlink,
        patch.object(strava_service.strava_client_service, "create_strava_client", return_value=client),
        patch.object(strava_service.core_cryptography, "decrypt_token_fernet", return_value="x"),
    ):
        error = None
        result = None
        try:
            result = strava_service.link_account("s", "c", user_id, db)
        except core_exceptions.DomainError as exc:
            error = exc
        return link, unlink, db, result, error


class TestLinkAccount:
    def test_the_owner_can_link(self):
        link, unlink, db, result, error = _link(user_id=1)

        assert error is None
        assert result.detail == "Strava linked successfully for user 1"
        link.assert_called_once()
        unlink.assert_not_called()
        db.commit.assert_called_once()

    def test_another_users_state_is_refused_and_left_untouched(self):
        link, unlink, _db, _result, error = _link(user_id=2)

        assert isinstance(error, core_exceptions.NotFoundError)
        link.assert_not_called()
        unlink.assert_not_called()

    def test_a_user_without_client_credentials_is_refused(self):
        link, _unlink, _db, _result, error = _link(user_id=1, has_credentials=False)

        assert isinstance(error, core_exceptions.InvalidInputError)
        link.assert_not_called()

    def test_a_failed_exchange_unlinks_again_and_answers_424(self):
        link, unlink, db, _result, error = _link(user_id=1, exchange_error=RuntimeError("bad code"))

        assert isinstance(error, core_exceptions.DependencyFailedError)
        assert error.status_code == 424
        link.assert_not_called()
        db.rollback.assert_called_once()
        unlink.assert_called_once()


class TestStoredCredentials:
    def test_the_client_is_stored_and_committed(self):
        db = MagicMock()
        with patch.object(strava_service.user_integrations_integration, "set_strava_client") as store:
            strava_service.set_client(7, 123, "secret", db)

        store.assert_called_once_with(7, 123, "secret", db)
        db.commit.assert_called_once()

    def test_the_state_is_stored_and_committed(self):
        db = MagicMock()
        with patch.object(strava_service.user_integrations_integration, "set_strava_state") as store:
            strava_service.set_state(7, "abc", db)

        store.assert_called_once_with(7, "abc", db)
        db.commit.assert_called_once()


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
    def test_a_refused_deauthorization_still_unlinks_and_clears_imported_data(self):
        client = MagicMock()
        client.deauthorize.side_effect = RuntimeError("revoked already")
        db = MagicMock()
        with (
            patch.object(strava_service.strava_client_service, "fetch_user_integrations_and_validate_token"),
            patch.object(strava_service.strava_client_service, "create_strava_client", return_value=client),
            patch.object(strava_service.gears_integration, "delete_all_strava_gear_for_user") as delete_gear,
            patch.object(strava_service.activity_integration, "delete_all_strava_activities") as delete_activities,
            patch.object(strava_service.user_integrations_integration, "unlink_strava_account") as unlink,
        ):
            strava_service.unlink_account(7, db)

        delete_gear.assert_called_once_with(7, db)
        delete_activities.assert_called_once_with(7, db)
        unlink.assert_called_once_with(7, db)
        db.commit.assert_called_once()
