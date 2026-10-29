"""Strava account linking: the state is single-use and the caller's, the exchange runs off the request."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.strava.constants as strava_constants
import modules.strava.link_service as strava_link_service
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.sync_state_store as strava_sync_state_store

Status = strava_constants.SyncStatus
LINK = strava_constants.SyncKind.LINK


@pytest.fixture
def oauth_states():
    return strava_oauth_state_store.StravaOAuthStateStore(platform_runtime.get_state())


@pytest.fixture
def states():
    return strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())


@pytest.fixture
def pool():
    """A pool that records what it is given instead of running it."""
    fake = MagicMock()
    with patch.object(strava_link_service, "_link_pool", fake):
        yield fake


_STATE = "s" * 43

_STATE = "s" * 43


def _start(oauth_states, states, *, user_id=1, stored_state=_STATE, sent_state=_STATE, has_credentials=True):
    if stored_state is not None:
        oauth_states.begin(1, stored_state)
    integrations = SimpleNamespace(
        strava_client_id="id" if has_credentials else None,
        strava_client_secret="stored" if has_credentials else None,
    )
    with (
        patch.object(strava_link_service.core_database, "SessionLocal"),
        patch.object(
            strava_link_service.user_integrations_integration, "get_user_integrations", return_value=integrations
        ),
    ):
        try:
            return (
                strava_link_service.start_link(
                    user_id, strava_schema.StravaLinkRequest(state=sent_state, code="c"), oauth_states, states
                ),
                None,
            )
        except core_exceptions.DomainError as exc:
            return None, exc


class TestStartLink:
    def test_the_owner_gets_a_queued_link_handed_to_the_pool(self, oauth_states, states, pool):
        result, error = _start(oauth_states, states)

        assert error is None
        assert result == strava_schema.StravaSyncStatus(kind=LINK, status=Status.QUEUED)
        assert states.get(1, LINK).status == Status.QUEUED
        pool.submit.assert_called_once_with(strava_link_service.run_link, 1, "c", states)

    def test_a_state_is_good_for_one_link_only(self, oauth_states, states, pool):
        _start(oauth_states, states)
        states.set_status(1, LINK, Status.COMPLETED)
        pool.reset_mock()

        _result, error = _start(oauth_states, states, stored_state=None)

        assert isinstance(error, core_exceptions.InvalidInputError)
        pool.submit.assert_not_called()

    def test_another_users_stored_state_is_never_consulted(self, oauth_states, states, pool):
        """The state is held per user, so user 2 cannot redeem the one user 1 stored."""
        _result, error = _start(oauth_states, states, user_id=2)

        assert isinstance(error, core_exceptions.InvalidInputError)
        pool.submit.assert_not_called()

    def test_a_wrong_state_is_refused_and_uses_up_the_stored_one(self, oauth_states, states, pool):
        _result, error = _start(oauth_states, states, sent_state="f" * 43)

        assert isinstance(error, core_exceptions.InvalidInputError)
        pool.submit.assert_not_called()
        assert oauth_states.consume(1, _STATE) is False

    def test_a_user_without_client_credentials_is_refused_and_no_link_is_recorded(self, oauth_states, states, pool):
        _result, error = _start(oauth_states, states, has_credentials=False)

        assert isinstance(error, core_exceptions.InvalidInputError)
        pool.submit.assert_not_called()
        assert states.get(1, LINK) is None

    def test_a_link_already_running_is_a_conflict(self, oauth_states, states, pool):
        _start(oauth_states, states)

        _result, error = _start(oauth_states, states)

        assert isinstance(error, core_exceptions.ConflictError)
        pool.submit.assert_called_once()

    def test_a_full_pool_is_refused_before_the_state_is_used_up(self, oauth_states, states, pool):
        pool.require_capacity.side_effect = core_local_pool.PoolFullError("full")

        _result, error = _start(oauth_states, states)

        assert isinstance(error, core_local_pool.PoolFullError)
        assert oauth_states.consume(1, _STATE) is True
        assert states.get(1, LINK) is None

    def test_a_link_that_cannot_start_frees_the_claim(self, oauth_states, states, pool):
        pool.submit.side_effect = core_local_pool.PoolFullError("full")

        _result, error = _start(oauth_states, states)

        assert isinstance(error, core_local_pool.PoolFullError)
        assert states.get(1, LINK).status == Status.FAILED
        assert states.begin(1, LINK) is True


def _run(states, *, exchange_error=None):
    states.begin(1, LINK)
    integrations = SimpleNamespace(strava_client_id="id", strava_client_secret="stored")
    client = MagicMock()
    client.exchange_code_for_token.return_value = {"access_token": "t"}
    if exchange_error:
        client.exchange_code_for_token.side_effect = exchange_error
    db = MagicMock()
    sessions = MagicMock()
    sessions.return_value.__enter__.return_value = db
    with (
        patch.object(strava_link_service.core_database, "SessionLocal", sessions),
        patch.object(
            strava_link_service.user_integrations_integration, "get_user_integrations", return_value=integrations
        ),
        patch.object(strava_link_service.user_integrations_integration, "link_strava_account") as link,
        patch.object(strava_link_service.strava_client_service, "create_strava_client", return_value=client),
        patch.object(strava_link_service.core_cryptography, "decrypt_token_fernet", return_value="x"),
    ):
        strava_link_service.run_link(1, "c", states)
    return link, db


class TestRunLinkTellsTheBrowser:
    @pytest.mark.parametrize("exchange_error", [None, RuntimeError("rejected")], ids=["completed", "failed"])
    def test_the_outcome_is_announced_once(self, states, exchange_error):
        with patch.object(strava_link_service.websocket_integration, "push_job_changed") as push:
            _run(states, exchange_error=exchange_error)

        push.assert_called_once_with(1, "strava:link")


class TestRunLink:
    def test_a_successful_exchange_stores_the_tokens_and_completes(self, states):
        link, db = _run(states)

        link.assert_called_once_with(1, {"access_token": "t"}, db)
        db.commit.assert_called_once()
        assert states.get(1, LINK).status == Status.COMPLETED

    def test_a_failed_exchange_is_recorded_without_storing_anything_and_frees_the_claim(self, states):
        link, db = _run(states, exchange_error=RuntimeError("secret-token-123 rejected"))

        link.assert_not_called()
        db.commit.assert_not_called()
        assert states.get(1, LINK).status == Status.FAILED
        assert states.begin(1, LINK) is True
