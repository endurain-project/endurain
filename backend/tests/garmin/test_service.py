"""Tests for the Garmin Connect link flow in garmin_service."""

from unittest.mock import MagicMock, patch

import garminconnect
import pytest
import requests
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.schema as garmin_schema
import modules.garmin.service as garmin_service

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
        patch.object(garmin_service.garminconnect, "Garmin", return_value=garmin) as factory,
        patch.object(garmin_service.core_database, "SessionLocal"),
        patch.object(garmin_service.user_integrations_integration, "link_garminconnect_account") as save,
        patch.object(garmin_service.garmin_token_utils, "serialize_garmin_token", return_value={"di_token": "enc"}),
    ):
        garmin_service.link_garminconnect(1, "me@example.com", "pw", mfa_codes, link_states, True)
    return factory, save


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
            (requests.exceptions.HTTPError("401"), Failure.INVALID_CREDENTIALS),
            (garminconnect.GarminConnectTooManyRequestsError("slow down"), Failure.TOO_MANY_REQUESTS),
            (TypeError("mfa"), Failure.INCORRECT_MFA),
            (RuntimeError("boom"), Failure.INTERNAL),
        ],
    )
    def test_each_failure_is_recorded_with_its_reason(self, stores, error, reason):
        _link(stores, _garmin(login=error))

        assert stores[1].get(1) == link_state_store.LinkState(status=Status.FAILED, reason=reason)

    def test_the_mfa_code_is_always_cleared(self, stores):
        stores[0].add_code(1, "stale")
        _link(stores, _garmin(login=RuntimeError("boom")))

        assert stores[0].has_code(1) is False

    def test_a_stale_code_does_not_answer_the_prompt(self, stores):
        mfa_codes = stores[0]
        mfa_codes.add_code(1, "stale")
        seen = []

        def login():
            seen.append(mfa_codes.has_code(1))

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

        assert garmin_service.wait_for_mfa_code(1, mfa_codes, link_states) == "123456"
        assert states == [Status.MFA_REQUIRED, Status.PENDING]

    def test_no_code_in_time_returns_none_and_stays_waiting(self, stores):
        mfa_codes, link_states = stores
        link_states.begin(1)

        with patch.object(garmin_constants, "MFA_WAIT_SECONDS", 2), patch.object(garmin_service.time, "sleep"):
            assert garmin_service.wait_for_mfa_code(1, mfa_codes, link_states) is None

        assert link_states.get(1).status == Status.MFA_REQUIRED


def test_starting_a_link_hands_it_to_the_dedicated_executor(stores):
    with patch.object(garmin_service, "_LINK_EXECUTOR") as executor:
        garmin_service.start_link(1, garmin_schema.GarminLogin(username="me", password="pw"), *stores)

    executor.submit.assert_called_once_with(garmin_service.link_garminconnect, 1, "me", "pw", *stores, False)


class TestLinkStatus:
    def test_an_expired_attempt_is_not_found(self, stores):
        with pytest.raises(core_exceptions.NotFoundError):
            garmin_service.get_link_status(1, stores[1])

    def test_a_recorded_attempt_is_reported(self, stores):
        stores[1].begin(1)

        assert garmin_service.get_link_status(1, stores[1]).status == Status.PENDING


class TestFetchUserIntegrationsAndValidateToken:
    def test_a_user_without_integrations_is_not_found(self):
        with (
            patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            garmin_service.fetch_user_integrations_and_validate_token(1, MagicMock())

    def test_an_unlinked_user_has_no_integrations_to_use(self):
        unlinked = MagicMock(garminconnect_token=None)
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=unlinked):
            assert garmin_service.fetch_user_integrations_and_validate_token(1, MagicMock()) is None

    def test_a_linked_user_is_returned(self):
        linked = MagicMock(garminconnect_token={"di_token": "enc"})
        with patch.object(garmin_service.user_integrations_integration, "get_user_integrations", return_value=linked):
            assert garmin_service.fetch_user_integrations_and_validate_token(1, MagicMock()) is linked
