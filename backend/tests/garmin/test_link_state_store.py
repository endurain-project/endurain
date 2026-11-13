"""Tests for garmin.link_state_store (provider-backed)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as link_state_store
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

Status = core_job_status.JobState
Failure = garmin_constants.LinkFailure


def _store() -> link_state_store.GarminLinkStateStore:
    return link_state_store.GarminLinkStateStore(state=MemoryState())


class TestBegin:
    def test_a_first_attempt_starts_running(self):
        store = _store()

        store.begin(MOCK_USER_ID, conflict="busy")
        assert store.get(MOCK_USER_ID) == link_state_store.LinkState(status=Status.RUNNING)

    def test_an_attempt_in_progress_blocks_another(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(MOCK_USER_ID, conflict="busy")

    def test_an_attempt_waiting_for_mfa_still_blocks_another(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")
        store.set_status(MOCK_USER_ID, Status.RUNNING, mfa_required=True)

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(MOCK_USER_ID, conflict="busy")

    def test_a_failed_attempt_can_be_retried(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")
        store.set_status(MOCK_USER_ID, Status.FAILED, Failure.INVALID_CREDENTIALS)

        store.begin(MOCK_USER_ID, conflict="busy")
        assert store.get(MOCK_USER_ID) == link_state_store.LinkState(status=Status.RUNNING)

    def test_a_completed_attempt_can_be_repeated(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")
        store.set_status(MOCK_USER_ID, Status.SUCCEEDED)

        store.begin(MOCK_USER_ID, conflict="busy")

    def test_the_claim_holds_even_when_the_state_entry_is_gone(self):
        state = MemoryState()
        store = link_state_store.GarminLinkStateStore(state=state)
        store.begin(MOCK_USER_ID, conflict="busy")
        state.delete(core_attempt_state.key("garmin", "link:state", str(MOCK_USER_ID)))

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(MOCK_USER_ID, conflict="busy")

    def test_users_do_not_block_each_other(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")

        store.begin(OTHER_USER_ID, conflict="busy")


class TestState:
    def test_no_attempt_reads_as_none(self):
        assert _store().get(uuid.UUID(int=99)) is None

    def test_a_failure_carries_its_error_code(self):
        store = _store()
        store.begin(MOCK_USER_ID, conflict="busy")

        store.set_status(MOCK_USER_ID, Status.FAILED, Failure.INCORRECT_MFA)

        assert store.get(MOCK_USER_ID) == link_state_store.LinkState(
            status=Status.FAILED, error_code=Failure.INCORRECT_MFA
        )

    def test_an_unavailable_backend_does_not_fail_the_attempt(self):
        state = MagicMock()
        state.set.side_effect = StateBackendUnavailableError("down")

        link_state_store.GarminLinkStateStore(state=state).set_status(MOCK_USER_ID, Status.SUCCEEDED)


def test_a_claim_is_not_left_behind_when_the_pending_state_cannot_be_written():
    state = MemoryState()
    store = link_state_store.GarminLinkStateStore(state=state)
    with (
        patch.object(state, "set", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        store.begin(MOCK_USER_ID, conflict="busy")

    store.begin(MOCK_USER_ID, conflict="busy")


def test_progress_renews_the_claim():
    state = MemoryState()
    store = link_state_store.GarminLinkStateStore(state=state, ttl_seconds=60)
    store.begin(MOCK_USER_ID, conflict="busy")
    with patch.object(state, "set") as write:
        store.set_status(MOCK_USER_ID, Status.RUNNING, mfa_required=True)

    assert core_attempt_state.key("garmin", "link:claim", str(MOCK_USER_ID)) in [
        call.args[0] for call in write.call_args_list
    ]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (b'{"status":"pending"}', link_state_store.LinkState(status=Status.RUNNING)),
        (b'{"status":"mfa_required"}', link_state_store.LinkState(status=Status.RUNNING, mfa_required=True)),
        (b'{"status":"completed"}', link_state_store.LinkState(status=Status.SUCCEEDED)),
        (
            b'{"status":"failed","reason":"incorrect_mfa"}',
            link_state_store.LinkState(status=Status.FAILED, error_code=Failure.INCORRECT_MFA),
        ),
    ],
)
def test_a_link_state_stored_with_the_old_names_reads_as_the_new_ones(stored, expected):
    assert link_state_store.LinkState.model_validate_json(stored) == expected
