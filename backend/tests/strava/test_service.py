"""Strava account linking: the state is single-use and the caller's, and a failed exchange keeps the setup."""

from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service


@pytest.fixture
def oauth_states():
    return strava_oauth_state_store.StravaOAuthStateStore(platform_runtime.get_state())


class TestStoredCredentials:
    def test_the_client_is_stored_and_committed(self):
        db = MagicMock()
        with (
            patch.object(strava_service.user_integrations_integration, "set_strava_client") as store,
            patch.object(
                strava_service.user_integrations_integration,
                "get_user_integrations",
                return_value=MagicMock(version=3),
            ),
        ):
            version = strava_service.set_client(
                7, strava_schema.StravaClientCredentials(client_id=123, client_secret="secret"), db, if_match='"2"'
            )

        store.assert_called_once_with(7, "123", "secret", db, if_match='"2"')
        db.commit.assert_called_once()
        assert version == 3

    def test_a_row_changed_by_another_request_is_a_stale_write_not_a_server_error(self):
        from sqlalchemy.orm.exc import StaleDataError

        db = MagicMock()
        with (
            patch.object(
                strava_service.user_integrations_integration, "set_strava_client", side_effect=StaleDataError()
            ),
            patch.object(strava_service.user_integrations_integration, "get_user_integrations", return_value=object()),
            pytest.raises(core_exceptions.PreconditionFailedError),
        ):
            strava_service.set_client(
                7, strava_schema.StravaClientCredentials(client_id=123, client_secret="secret"), db, if_match='"2"'
            )

        db.commit.assert_not_called()


class TestOAuthState:
    def test_a_begun_state_is_consumed_once(self, oauth_states):
        state = strava_service.begin_state(7, oauth_states)

        assert oauth_states.consume(7, state) is True
        assert oauth_states.consume(7, state) is False

    def test_the_state_is_unguessable_and_different_each_time(self, oauth_states):
        states = {strava_service.begin_state(7, oauth_states) for _ in range(5)}

        assert len(states) == 5
        assert all(len(state) >= 32 for state in states)

    def test_a_cleared_state_can_no_longer_be_used(self, oauth_states):
        state = strava_service.begin_state(7, oauth_states)
        strava_service.clear_state(7, oauth_states)

        assert oauth_states.consume(7, state) is False

    def test_a_new_state_replaces_the_old_one(self, oauth_states):
        old = strava_service.begin_state(7, oauth_states)
        strava_service.begin_state(7, oauth_states)

        assert oauth_states.consume(7, old) is False


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
            patch.object(strava_service.core_database, "SessionLocal", sessions),
            patch.object(
                strava_service.strava_client_service,
                "fetch_user_integrations_and_validate_token",
                return_value=object() if linked else None,
            ),
            patch.object(strava_service.strava_client_service, "create_strava_client", return_value=client),
            patch.object(strava_service.gears_integration, "delete_all_strava_gear_for_user") as delete_gear,
            patch.object(
                strava_service.activity_integration, "delete_all_strava_activities", return_value=0
            ) as delete_activities,
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


class TestUnlinkDeletesInBatches:
    def test_activities_are_deleted_batch_by_batch_and_the_unlink_commits_last(self):
        batch = strava_constants.UNLINK_DELETE_BATCH_SIZE
        order: list[str] = []
        batches = iter([batch, batch, 3])
        with (
            patch.object(strava_service.core_database, "SessionLocal"),
            patch.object(
                strava_service.strava_client_service,
                "fetch_user_integrations_and_validate_token",
                return_value=object(),
            ),
            patch.object(strava_service.strava_client_service, "create_strava_client"),
            patch.object(
                strava_service.activity_integration,
                "delete_all_strava_activities",
                side_effect=lambda *_a, **_k: order.append("batch") or next(batches),
            ) as delete_activities,
            patch.object(
                strava_service.gears_integration,
                "delete_all_strava_gear_for_user",
                side_effect=lambda *_a, **_k: order.append("gear"),
            ),
            patch.object(
                strava_service.user_integrations_integration,
                "unlink_strava_account",
                side_effect=lambda *_a, **_k: order.append("unlink"),
            ),
        ):
            assert strava_service.unlink_account(7) is True

        assert delete_activities.call_count == 3
        assert all(call.kwargs["limit"] == batch for call in delete_activities.call_args_list)
        assert order == ["batch", "batch", "batch", "gear", "unlink"]
