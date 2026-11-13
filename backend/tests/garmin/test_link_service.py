"""Tests for the Garmin Connect link flow in garmin_link_service."""

import uuid
from unittest.mock import MagicMock, patch

import garminconnect
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.sync_runner as core_sync_runner
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.integration_service as garmin_integration
import modules.garmin.link_service as garmin_link_service
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.schema as garmin_schema
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

Status = core_job_status.JobState
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
    _link.job = link_states.begin(MOCK_USER_ID, conflict="busy")
    with (
        patch.object(garmin_link_service.websocket_integration, "push_job_changed") as push,
        patch.object(garmin_link_service.garminconnect, "Garmin", return_value=garmin) as factory,
        patch.object(garmin_link_service.core_database, "SessionLocal"),
        patch.object(garmin_link_service.user_integrations_integration, "link_garminconnect_account") as save,
        patch.object(
            garmin_link_service.garmin_token_utils, "serialize_garmin_token", return_value={"di_token": "enc"}
        ),
    ):
        garmin_link_service.link_garminconnect(MOCK_USER_ID, "me@example.com", "pw", mfa_codes, link_states, True)
    _link.push = push
    return factory, save


class TestLinkTellsTheBrowser:
    """The dialog polls the link; a hint lets it stop waiting the moment the outcome is recorded."""

    def test_a_completed_link_is_announced_once(self, stores):
        _link(stores, _garmin())

        _link.push.assert_called_once_with(MOCK_USER_ID, _link.job.id, "garmin_link")

    def test_a_failed_link_is_announced_once(self, stores):
        _link(stores, _garmin(login=RuntimeError("boom")))

        _link.push.assert_called_once_with(MOCK_USER_ID, _link.job.id, "garmin_link")

    def test_asking_for_the_mfa_code_is_announced(self, stores):
        mfa_codes, link_states = stores
        job = link_states.begin(MOCK_USER_ID, conflict="busy")
        mfa_codes.add_code(MOCK_USER_ID, "123456")

        with patch.object(garmin_link_service.websocket_integration, "push_job_changed") as push:
            garmin_link_service.wait_for_mfa_code(MOCK_USER_ID, mfa_codes, link_states)

        push.assert_called_once_with(MOCK_USER_ID, job.id, "garmin_link")


class TestLinkGarminconnect:
    def test_a_successful_login_stores_the_token_and_completes(self, stores):
        factory, save = _link(stores, _garmin())

        assert stores[1].get(MOCK_USER_ID) == link_state_store.LinkState(status=Status.SUCCEEDED)
        save.assert_called_once()
        assert factory.call_args.kwargs["is_cn"] is True

    def test_a_missing_token_is_a_credentials_failure(self, stores):
        _, save = _link(stores, _garmin(has_token=False))

        assert stores[1].get(MOCK_USER_ID).error_code == Failure.INVALID_CREDENTIALS
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

        assert stores[1].get(MOCK_USER_ID) == link_state_store.LinkState(status=Status.FAILED, error_code=reason)

    def test_a_rejection_after_the_mfa_prompt_is_an_incorrect_code(self, stores):
        link_states = stores[1]
        garmin = _garmin()
        prompts = []

        def login():
            prompts.append(garmin_link_service.garminconnect.Garmin.call_args.kwargs["prompt_mfa"]())
            raise garminconnect.GarminConnectAuthenticationError("MFA verification failed")

        garmin.login.side_effect = login
        with patch.object(garmin_link_service, "wait_for_mfa_code", return_value="123456"):
            _link(stores, garmin)

        assert prompts == ["123456"]
        assert link_states.get(MOCK_USER_ID).error_code == Failure.INCORRECT_MFA

    def test_an_mfa_code_that_never_arrives_fails_without_reaching_garmin(self, stores):
        link_states = stores[1]
        garmin = _garmin()
        sent = []

        def login():
            sent.append(garmin_link_service.garminconnect.Garmin.call_args.kwargs["prompt_mfa"]())

        garmin.login.side_effect = login
        with (
            patch.object(garmin_constants, "MFA_WAIT_SECONDS", 1),
            patch.object(garmin_link_service.time, "sleep"),
            jasil_testing.capture_audit() as audit,
        ):
            _, save = _link(stores, garmin)

        assert sent == []
        assert link_states.get(MOCK_USER_ID) == link_state_store.LinkState(
            status=Status.FAILED, error_code=Failure.INCORRECT_MFA
        )
        save.assert_not_called()
        entry = audit.assert_audited(garmin_audit_actions.ACCOUNT_LINK.id, outcome="failure")
        assert entry.details == {"reason": "incorrect_mfa"}

    def test_an_mfa_timeout_is_an_incorrect_code_through_the_librarys_login_wrapping(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(MOCK_USER_ID, conflict="busy")

        def client_login(_self, _email, _password, prompt_mfa=None, **_kwargs):
            prompt_mfa()

        # The real Garmin.login runs, so its final handler rewraps the timeout as a connection error.
        with (
            patch.object(garminconnect.client.Client, "login", client_login),
            patch.object(garmin_constants, "MFA_WAIT_SECONDS", 1),
            patch.object(garmin_link_service.time, "sleep"),
            patch.object(garmin_link_service.websocket_integration, "push_job_changed"),
            jasil_testing.capture_audit() as audit,
        ):
            garmin_link_service.link_garminconnect(MOCK_USER_ID, "me@example.com", "pw", mfa_codes, link_states, False)

        assert link_states.get(MOCK_USER_ID) == link_state_store.LinkState(
            status=Status.FAILED, error_code=Failure.INCORRECT_MFA
        )
        entry = audit.assert_audited(garmin_audit_actions.ACCOUNT_LINK.id, outcome="failure")
        assert entry.details == {"reason": "incorrect_mfa"}

    def test_a_rejection_without_an_mfa_prompt_is_invalid_credentials(self, stores):
        _link(stores, _garmin(login=garminconnect.GarminConnectAuthenticationError("bad password")))

        assert stores[1].get(MOCK_USER_ID).error_code == Failure.INVALID_CREDENTIALS

    def test_the_mfa_code_is_always_cleared(self, stores):
        stores[0].add_code(MOCK_USER_ID, "stale")
        _link(stores, _garmin(login=RuntimeError("boom")))

        assert stores[0].get_code(MOCK_USER_ID) is None

    def test_a_stale_code_does_not_answer_the_prompt(self, stores):
        mfa_codes = stores[0]
        mfa_codes.add_code(MOCK_USER_ID, "stale")
        seen = []

        def login():
            seen.append(mfa_codes.get_code(MOCK_USER_ID) is not None)

        _link(stores, _garmin(login=login))

        assert seen == [False]


class TestWaitForMfaCode:
    def test_the_prompt_is_the_shared_state_and_the_code_resumes_the_attempt(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(MOCK_USER_ID, conflict="busy")
        states = []
        real_set = link_states.set_status
        link_states.set_status = lambda user_id, status, reason=None, *, mfa_required=False: (
            states.append(mfa_required),
            real_set(user_id, status, mfa_required=mfa_required),
        )
        mfa_codes.add_code(MOCK_USER_ID, "123456")

        assert garmin_link_service.wait_for_mfa_code(MOCK_USER_ID, mfa_codes, link_states) == "123456"
        assert states == [True, False]

    def test_no_code_in_time_raises_and_stays_waiting(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(MOCK_USER_ID, conflict="busy")

        with (
            patch.object(garmin_constants, "MFA_WAIT_SECONDS", 2),
            patch.object(garmin_link_service.time, "sleep"),
            pytest.raises(garmin_link_service._MfaCodeTimeoutError),
        ):
            garmin_link_service.wait_for_mfa_code(MOCK_USER_ID, mfa_codes, link_states)

        assert link_states.get(MOCK_USER_ID).mfa_required is True


def test_starting_a_link_hands_it_to_the_link_pool(stores):
    with patch.object(garmin_link_service, "_link_pool") as pool:
        garmin_link_service.start_link(MOCK_USER_ID, garmin_schema.GarminLogin(username="me", password="pw"), *stores)

    pool.submit.assert_called_once_with(
        garmin_link_service.link_garminconnect, MOCK_USER_ID, "me", "pw", *stores, False
    )


def test_a_link_beyond_the_capacity_is_refused_and_leaves_no_attempt_behind(stores, blocked_pool, monkeypatch):
    monkeypatch.setattr(garmin_link_service, "link_garminconnect", lambda *args: blocked_pool.release.wait(5))
    monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(core_sync_runner.MAX_CONCURRENT_LINKS))
    login = garmin_schema.GarminLogin(username="me", password="pw")
    for user_id in map(
        uuid.UUID, (f"00000000-0000-4000-8000-{n:012d}" for n in range(core_sync_runner.MAX_CONCURRENT_LINKS))
    ):
        garmin_link_service.start_link(user_id, login, *stores)

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        garmin_link_service.start_link(uuid.UUID(int=99), login, *stores)

    assert stores[1].get(uuid.UUID(int=99)) is None


def test_a_refused_duplicate_link_takes_no_capacity(stores, blocked_pool, monkeypatch):
    monkeypatch.setattr(garmin_link_service, "link_garminconnect", lambda *args: blocked_pool.release.wait(5))
    monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(2))
    login = garmin_schema.GarminLogin(username="me", password="pw")
    garmin_link_service.start_link(MOCK_USER_ID, login, *stores)
    for _ in range(3):
        with pytest.raises(core_exceptions.ConflictError):
            garmin_link_service.start_link(MOCK_USER_ID, login, *stores)

    assert garmin_link_service.start_link(OTHER_USER_ID, login, *stores).status == Status.RUNNING


class TestSubmitMfaCode:
    def test_a_code_is_taken_while_the_login_waits_for_it(self, stores):
        stores[1].begin(MOCK_USER_ID, conflict="busy")
        stores[1].set_status(MOCK_USER_ID, Status.RUNNING, mfa_required=True)

        garmin_link_service.submit_mfa_code(MOCK_USER_ID, "123456", *stores)

        assert stores[0].get_code(MOCK_USER_ID) == "123456"

    def test_a_code_with_no_login_waiting_is_a_conflict(self, stores):
        stores[1].begin(MOCK_USER_ID, conflict="busy")

        with pytest.raises(core_exceptions.ConflictError):
            garmin_link_service.submit_mfa_code(MOCK_USER_ID, "123456", *stores)

        assert stores[0].get_code(MOCK_USER_ID) is None


class TestReadLinkJob:
    def test_a_job_reads_with_its_id_and_kind(self):
        state = MemoryState()
        store = link_state_store.GarminLinkStateStore(state=state)
        job = store.begin(MOCK_USER_ID, conflict="busy")
        store.set_status(MOCK_USER_ID, Status.RUNNING, mfa_required=True)

        read = garmin_integration.read_link_job(job, state)

        assert (read.id, read.kind, read.status, read.mfa_required) == (job.id, "garmin_link", Status.RUNNING, True)

    def test_an_earlier_job_reads_as_gone_once_the_user_links_again(self):
        state = MemoryState()
        store = link_state_store.GarminLinkStateStore(state=state)
        first = store.begin(MOCK_USER_ID, conflict="busy")
        store.set_status(MOCK_USER_ID, Status.FAILED, garmin_constants.LinkFailure.INVALID_CREDENTIALS)
        second = store.begin(MOCK_USER_ID, conflict="busy")

        assert garmin_integration.read_link_job(first, state) is None
        assert garmin_integration.read_link_job(second, state).id == second.id

    def test_an_expired_job_reads_as_gone(self):
        state = MemoryState()
        store = link_state_store.GarminLinkStateStore(state=state)
        job = store.begin(MOCK_USER_ID, conflict="busy")
        store.release(MOCK_USER_ID)
        state.delete(core_attempt_state.key("garmin", "link:state", str(MOCK_USER_ID)))

        assert garmin_integration.read_link_job(job, state) is None


def test_a_link_that_cannot_start_releases_its_claim(stores):
    mfa_codes, link_states = stores
    with patch.object(garmin_link_service, "_link_pool") as pool:
        pool.submit.side_effect = RuntimeError("shut down")
        with pytest.raises(RuntimeError):
            garmin_link_service.start_link(
                MOCK_USER_ID, garmin_schema.GarminLogin(username="u", password="p"), mfa_codes, link_states
            )

    link_states.begin(MOCK_USER_ID, conflict="busy")


def test_the_password_does_not_appear_in_the_login_repr():
    login = garmin_schema.GarminLogin(username="me@example.com", password="s3cret")

    assert "s3cret" not in repr(login)
    assert login.password.get_secret_value() == "s3cret"
