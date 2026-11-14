"""Strava account linking: the state is single-use and the caller's, and a failed exchange keeps the setup."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import jasil.testing as jasil_testing
import pytest
import requests

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service
from tests._helpers.auth import MOCK_USER_ID

_STEP_UP = auth_schema.StepUpVerification(current_password="pw")
_verify = MagicMock()


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
                MOCK_USER_ID,
                strava_schema.StravaClientCredentials(client_id=123, client_secret="secret", step_up=_STEP_UP),
                _verify,
                db,
                if_match='"2"',
            )

        store.assert_called_once_with(MOCK_USER_ID, "123", "secret", db, if_match='"2"')
        # One commit for the verified step-up, one for the stored client.
        assert db.commit.call_count == 2
        assert version == 3

    def test_the_step_up_is_verified_for_the_client_action_before_anything_is_stored(self):
        verify = MagicMock(side_effect=core_exceptions.StepUpFailedError("no"))
        with (
            patch.object(strava_service.user_integrations_integration, "set_strava_client") as store,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            strava_service.set_client(
                MOCK_USER_ID,
                strava_schema.StravaClientCredentials(client_id=123, client_secret="secret", step_up=_STEP_UP),
                verify,
                MagicMock(),
                if_match='"2"',
            )

        verify.assert_called_once_with(_STEP_UP, identity_providers_constants.StepUpAction.STRAVA_CLIENT_SET)
        store.assert_not_called()

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
                MOCK_USER_ID,
                strava_schema.StravaClientCredentials(client_id=123, client_secret="secret", step_up=_STEP_UP),
                _verify,
                db,
                if_match='"2"',
            )

        # Only the verified step-up was committed.
        assert db.commit.call_count == 1


class TestOAuthState:
    def test_a_begun_state_is_consumed_once(self, oauth_states):
        state = strava_service.begin_state(MOCK_USER_ID, oauth_states)

        assert oauth_states.consume(MOCK_USER_ID, state) is True
        assert oauth_states.consume(MOCK_USER_ID, state) is False

    def test_the_state_is_unguessable_and_different_each_time(self, oauth_states):
        states = {strava_service.begin_state(MOCK_USER_ID, oauth_states) for _ in range(5)}

        assert len(states) == 5
        assert all(len(state) >= 32 for state in states)

    def test_a_new_state_replaces_the_old_one(self, oauth_states):
        old = strava_service.begin_state(MOCK_USER_ID, oauth_states)
        strava_service.begin_state(MOCK_USER_ID, oauth_states)

        assert oauth_states.consume(MOCK_USER_ID, old) is False


class TestUnlinkAccount:
    def _run(self, *, linked=True, deauthorize_error=None, refresh_error=None, refreshed=None):
        client = MagicMock()
        stale = object()
        refreshed = object() if refreshed is None else refreshed
        refresh = MagicMock(side_effect=refresh_error)
        rate_limits = MagicMock()
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
                side_effect=[stale, refreshed] if linked else [None],
            ),
            patch.object(strava_service.strava_client_service, "refresh_user_strava_token", refresh),
            patch.object(
                strava_service.strava_client_service, "create_strava_client", return_value=client
            ) as create_client,
            patch.object(strava_service.gears_integration, "delete_all_strava_gear_for_user") as delete_gear,
            patch.object(
                strava_service.activity_integration, "delete_all_strava_activities", return_value=0
            ) as delete_activities,
            patch.object(strava_service.user_integrations_integration, "unlink_strava_account") as unlink,
        ):
            result = strava_service.unlink_account(MOCK_USER_ID, rate_limits)
        self.refresh, self.create_client, self.rate_limits, self.refreshed = (
            refresh,
            create_client,
            rate_limits,
            refreshed,
        )
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
            deauthorize_error=requests.HTTPError("revoked already")
        )

        assert result is True
        delete_gear.assert_called_once()
        delete_activities.assert_called_once()
        unlink.assert_called_once()

    def test_an_expired_token_is_refreshed_before_deauthorizing_with_the_new_token(self):
        self._run()

        self.refresh.assert_called_once_with(MOCK_USER_ID, self.rate_limits)
        self.create_client.assert_called_once_with(self.refreshed)

    def test_a_revoked_grant_has_nothing_to_deauthorize_but_still_unlinks_locally(self):
        result, client, delete_gear, delete_activities, unlink, _ = self._run(
            refresh_error=strava_client_service.StravaTokenRejectedError("revoked")
        )

        assert result is True
        client.deauthorize.assert_not_called()
        delete_gear.assert_called_once()
        delete_activities.assert_called_once()
        unlink.assert_called_once()

    def test_a_refresh_that_fails_otherwise_still_unlinks_locally(self):
        result, client, *_rest, unlink, _ = self._run(
            refresh_error=core_exceptions.DependencyFailedError("The Strava token could not be refreshed")
        )

        assert result is True
        client.deauthorize.assert_not_called()
        unlink.assert_called_once()

    def test_a_rate_limited_refresh_leaves_the_account_linked_to_try_again(self):
        error = core_exceptions.TooManyRequestsError("later", scope=core_exceptions.TooManyRequestsScope.PROVIDER)
        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._run(refresh_error=error)

    def test_a_bug_in_the_deauthorization_is_not_swallowed(self):
        with pytest.raises(RuntimeError):
            self._run(deauthorize_error=RuntimeError("bug"))

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
            patch.object(strava_service.strava_client_service, "refresh_user_strava_token"),
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
            assert strava_service.unlink_account(MOCK_USER_ID, MagicMock()) is True

        assert delete_activities.call_count == 3
        assert all(call.kwargs["limit"] == batch for call in delete_activities.call_args_list)
        assert order == ["batch", "batch", "batch", "gear", "unlink"]


class TestDeleteRevokedData:
    DAY = timedelta(days=1)

    def _integrations(self, *, revoked_days_ago: float | None, token: str | None = None):
        revoked_at = None if revoked_days_ago is None else datetime.now(UTC) - timedelta(days=revoked_days_ago)
        return MagicMock(strava_revoked_at=revoked_at, strava_token=token)

    def _run(self, integrations, *, batches=(2,)):
        order: list[str] = []
        sessions = MagicMock()
        sessions.return_value.__enter__.side_effect = lambda: MagicMock()
        batch_counts = iter(batches)
        with (
            patch.object(strava_service.core_database, "SessionLocal", sessions),
            patch.object(
                strava_service.user_integrations_integration, "get_user_integrations", return_value=integrations
            ),
            patch.object(
                strava_service.activity_integration,
                "delete_all_strava_activities",
                side_effect=lambda *_a, **_k: order.append("batch") or next(batch_counts),
            ),
            patch.object(
                strava_service.gears_integration,
                "delete_all_strava_gear_for_user",
                side_effect=lambda *_a, **_k: order.append("gear"),
            ),
            patch.object(
                strava_service.user_integrations_integration,
                "clear_strava_revoked_at",
                side_effect=lambda *_a, **_k: order.append("clear"),
            ),
            patch.object(
                strava_service.notifications_integration,
                "create_strava_data_deleted_notification",
                side_effect=lambda *_a, **_k: order.append("notify") or ("n", "ws"),
            ),
            patch.object(strava_service.notifications_integration, "push_notification") as push,
            patch.object(strava_service.strava_client_service, "create_strava_client") as create_client,
            jasil_testing.capture_audit() as audit,
        ):
            result = strava_service.delete_revoked_data(MOCK_USER_ID)
        return result, order, push, create_client, audit

    def test_data_of_a_user_revoked_past_the_grace_period_is_deleted_and_the_user_told(self):
        result, order, push, create_client, audit = self._run(self._integrations(revoked_days_ago=8))

        assert result is True
        assert order == ["batch", "gear", "clear", "notify"]
        push.assert_called_once_with(MOCK_USER_ID, "n", "ws")
        create_client.assert_not_called()
        entry = audit.assert_audited(
            strava_audit_actions.DATA_DELETE.id,
            target_type="user",
            target_id=str(MOCK_USER_ID),
            target_owner_id=str(MOCK_USER_ID),
        )
        assert entry.details == {"activity_count": 2}

    def test_a_user_still_inside_the_grace_period_is_left_alone(self):
        result, order, push, _client, audit = self._run(self._integrations(revoked_days_ago=3))

        assert result is False
        assert order == []
        push.assert_not_called()
        audit.assert_not_audited(strava_audit_actions.DATA_DELETE.id)

    def test_a_user_who_relinked_is_left_alone(self):
        result, order, _push, _client, _audit = self._run(self._integrations(revoked_days_ago=None))
        assert (result, order) == (False, [])

        result, order, _push, _client, _audit = self._run(self._integrations(revoked_days_ago=8, token="enc"))
        assert (result, order) == (False, [])

    def test_activities_are_deleted_in_batches_before_the_closing_transaction(self):
        batch = strava_constants.UNLINK_DELETE_BATCH_SIZE
        _result, order, _push, _client, audit = self._run(
            self._integrations(revoked_days_ago=8), batches=(batch, batch, 3)
        )

        assert order == ["batch", "batch", "batch", "gear", "clear", "notify"]
        assert audit.assert_audited(strava_audit_actions.DATA_DELETE.id).details == {"activity_count": 2 * batch + 3}
