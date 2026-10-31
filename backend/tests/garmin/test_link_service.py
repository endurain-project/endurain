"""Tests for the Garmin Connect link flow in garmin_link_service."""

from unittest.mock import MagicMock, patch

import garminconnect
import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import core.sync_runner as core_sync_runner
import modules.garmin.constants as garmin_constants
import modules.garmin.link_service as garmin_link_service
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.schema as garmin_schema

Status = garmin_constants.LinkStatus
Failure = garmin_constants.LinkFailure


@pytest.fixture
def stores():
    state = MemoryState()
    return mfa_code_store.GarminMFACodeStore(state=state), link_state_store.GarminLinkStateStore(state=state)


def _garmin(login=None, has_token=True):
    garmin = MagicMock()
    garmin.client.di_token = "enc" if has_token else None
    garmin.login.side_effect = login
    return garmin


def _link(stores, garmin):
    mfa_codes, link_states = stores
    link_states.begin(1)
    with (
        patch.object(garmin_link_service.websocket_integration, "push_job_changed") as push,
        patch.object(garmin_link_service.garminconnect, "Garmin", return_value=garmin) as factory,
        patch.object(garmin_link_service.core_database, "SessionLocal"),
        patch.object(garmin_link_service.user_integrations_integration, "link_garminconnect_account") as save,
        patch.object(
            garmin_link_service.garmin_token_utils, "serialize_garmin_token", return_value={"di_token": "enc"}
        ),
    ):
        garmin_link_service.link_garminconnect(1, "me@example.com", "pw", mfa_codes, link_states, True)
    _link.push = push
    return factory, save


class TestLinkTellsTheBrowser:
    """The dialog polls the link; a hint lets it stop waiting the moment the outcome is recorded."""

    def test_a_completed_link_is_announced_once(self, stores):
        _link(stores, _garmin())

        _link.push.assert_called_once_with(1, "garmin-link")

    def test_a_failed_link_is_announced_once(self, stores):
        _link(stores, _garmin(login=RuntimeError("boom")))

        _link.push.assert_called_once_with(1, "garmin-link")

    def test_asking_for_the_mfa_code_is_announced(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(1)
        mfa_codes.add_code(1, "123456")

        with patch.object(garmin_link_service.websocket_integration, "push_job_changed") as push:
            garmin_link_service.wait_for_mfa_code(1, mfa_codes, link_states)

        push.assert_called_once_with(1, "garmin-link")


class TestLinkGarminconnect:
    def test_a_successful_login_stores_the_token_and_completes(self, stores):
        factory, save = _link(stores, _garmin())

        assert stores[1].get(1) == link_state_store.LinkState(status=Status.COMPLETED)
        save.assert_called_once()
        assert factory.call_args.kwargs["is_cn"] is True

    def test_a_missing_token_is_a_credentials_failure(self, stores):
        _, save = _link(stores, _garmin(has_token=False))

        assert stores[1].get(1).reason == Failure.INVALID_CREDENTIALS
        save.assert_not_called()

    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (garminconnect.GarminConnectAuthenticationError("no"), Failure.INVALID_CREDENTIALS),
            (garminconnect.GarminConnectTooManyRequestsError("slow down"), Failure.TOO_MANY_REQUESTS),
            (garminconnect.GarminConnectConnectionError("down"), Failure.INTERNAL),
            (TypeError("not an mfa problem"), Failure.INTERNAL),
            (RuntimeError("boom"), Failure.INTERNAL),
        ],
    )
    def test_each_failure_is_recorded_with_its_reason(self, stores, error, reason):
        _link(stores, _garmin(login=error))

        assert stores[1].get(1) == link_state_store.LinkState(status=Status.FAILED, reason=reason)

    def test_a_rejection_after_the_mfa_prompt_is_an_incorrect_code(self, stores):
        link_states = stores[1]
        garmin = _garmin()
        prompts = []

        def login():
            prompts.append(garmin_link_service.garminconnect.Garmin.call_args.kwargs["prompt_mfa"]())
            raise garminconnect.GarminConnectAuthenticationError("MFA verification failed")

        garmin.login.side_effect = login
        with patch.object(garmin_link_service, "wait_for_mfa_code", return_value=None):
            _link(stores, garmin)

        assert prompts == [None]
        assert link_states.get(1).reason == Failure.INCORRECT_MFA

    def test_a_rejection_without_an_mfa_prompt_is_invalid_credentials(self, stores):
        _link(stores, _garmin(login=garminconnect.GarminConnectAuthenticationError("bad password")))

        assert stores[1].get(1).reason == Failure.INVALID_CREDENTIALS

    def test_the_mfa_code_is_always_cleared(self, stores):
        stores[0].add_code(1, "stale")
        _link(stores, _garmin(login=RuntimeError("boom")))

        assert stores[0].get_code(1) is None

    def test_a_stale_code_does_not_answer_the_prompt(self, stores):
        mfa_codes = stores[0]
        mfa_codes.add_code(1, "stale")
        seen = []

        def login():
            seen.append(mfa_codes.get_code(1) is not None)

        _link(stores, _garmin(login=login))

        assert seen == [False]


class TestWaitForMfaCode:
    def test_the_prompt_is_the_shared_state_and_the_code_resumes_the_attempt(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(1)
        states = []
        real_set = link_states.set_status
        link_states.set_status = lambda user_id, status, reason=None: (states.append(status), real_set(user_id, status))
        mfa_codes.add_code(1, "123456")

        assert garmin_link_service.wait_for_mfa_code(1, mfa_codes, link_states) == "123456"
        assert states == [Status.MFA_REQUIRED, Status.PENDING]

    def test_no_code_in_time_returns_none_and_stays_waiting(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(1)

        with patch.object(garmin_constants, "MFA_WAIT_SECONDS", 2), patch.object(garmin_link_service.time, "sleep"):
            assert garmin_link_service.wait_for_mfa_code(1, mfa_codes, link_states) is None

        assert link_states.get(1).status == Status.MFA_REQUIRED


def test_starting_a_link_hands_it_to_the_link_pool(stores):
    with patch.object(garmin_link_service, "_link_pool") as pool:
        garmin_link_service.start_link(1, garmin_schema.GarminLogin(username="me", password="pw"), *stores)

    pool.submit.assert_called_once_with(garmin_link_service.link_garminconnect, 1, "me", "pw", *stores, False)


def test_a_link_beyond_the_capacity_is_refused_and_leaves_no_attempt_behind(stores, blocked_pool, monkeypatch):
    monkeypatch.setattr(garmin_link_service, "link_garminconnect", lambda *args: blocked_pool.release.wait(5))
    monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(core_sync_runner.MAX_CONCURRENT_LINKS))
    login = garmin_schema.GarminLogin(username="me", password="pw")
    for user_id in range(core_sync_runner.MAX_CONCURRENT_LINKS):
        garmin_link_service.start_link(user_id, login, *stores)

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        garmin_link_service.start_link(99, login, *stores)

    assert stores[1].get(99) is None


def test_a_refused_duplicate_link_takes_no_capacity(stores, blocked_pool, monkeypatch):
    monkeypatch.setattr(garmin_link_service, "link_garminconnect", lambda *args: blocked_pool.release.wait(5))
    monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(2))
    login = garmin_schema.GarminLogin(username="me", password="pw")
    garmin_link_service.start_link(1, login, *stores)
    for _ in range(3):
        with pytest.raises(core_exceptions.ConflictError):
            garmin_link_service.start_link(1, login, *stores)

    assert garmin_link_service.start_link(2, login, *stores).status == Status.PENDING


class TestSubmitMfaCode:
    def test_a_code_is_taken_while_the_login_waits_for_it(self, stores):
        stores[1].begin(1)
        stores[1].set_status(1, Status.MFA_REQUIRED)

        garmin_link_service.submit_mfa_code(1, "123456", *stores)

        assert stores[0].get_code(1) == "123456"

    def test_a_code_with_no_login_waiting_is_a_conflict(self, stores):
        stores[1].begin(1)

        with pytest.raises(core_exceptions.ConflictError):
            garmin_link_service.submit_mfa_code(1, "123456", *stores)

        assert stores[0].get_code(1) is None


class TestLinkStatus:
    def test_an_expired_attempt_is_not_found(self, stores):
        with pytest.raises(core_exceptions.NotFoundError):
            garmin_link_service.get_link_status(1, stores[1])

    def test_a_recorded_attempt_is_reported(self, stores):
        stores[1].begin(1)

        assert garmin_link_service.get_link_status(1, stores[1]).status == Status.PENDING


def test_a_link_that_cannot_start_releases_its_claim(stores):
    mfa_codes, link_states = stores
    with patch.object(garmin_link_service, "_link_pool") as pool:
        pool.submit.side_effect = RuntimeError("shut down")
        with pytest.raises(RuntimeError):
            garmin_link_service.start_link(
                1, garmin_schema.GarminLogin(username="u", password="p"), mfa_codes, link_states
            )

    assert link_states.begin(1) is True


def test_the_password_does_not_appear_in_the_login_repr():
    login = garmin_schema.GarminLogin(username="me@example.com", password="s3cret")

    assert "s3cret" not in repr(login)
    assert login.password.get_secret_value() == "s3cret"
