"""Tests for garmin.link_state_store (provider-backed)."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as link_state_store
import modules.garmin.state_store as garmin_state_store

Status = garmin_constants.LinkStatus
Failure = garmin_constants.LinkFailure


def _store() -> link_state_store.GarminLinkStateStore:
    return link_state_store.GarminLinkStateStore(state=MemoryState())


class TestBegin:
    def test_a_first_attempt_starts_pending(self):
        store = _store()

        assert store.begin(1) is True
        assert store.get(1) == link_state_store.LinkState(status=Status.PENDING)

    def test_an_attempt_in_progress_blocks_another(self):
        store = _store()
        store.begin(1)

        assert store.begin(1) is False

    def test_an_attempt_waiting_for_mfa_still_blocks_another(self):
        store = _store()
        store.begin(1)
        store.set_status(1, Status.MFA_REQUIRED)

        assert store.begin(1) is False

    def test_a_failed_attempt_can_be_retried(self):
        store = _store()
        store.begin(1)
        store.set_status(1, Status.FAILED, Failure.INVALID_CREDENTIALS)

        assert store.begin(1) is True
        assert store.get(1) == link_state_store.LinkState(status=Status.PENDING)

    def test_a_completed_attempt_can_be_repeated(self):
        store = _store()
        store.begin(1)
        store.set_status(1, Status.COMPLETED)

        assert store.begin(1) is True

    def test_the_claim_holds_even_when_the_state_entry_is_gone(self):
        state = MemoryState()
        store = link_state_store.GarminLinkStateStore(state=state)
        store.begin(1)
        state.delete(garmin_state_store.key("link:state", "1"))

        assert store.begin(1) is False

    def test_users_do_not_block_each_other(self):
        store = _store()
        store.begin(1)

        assert store.begin(2) is True


class TestState:
    def test_no_attempt_reads_as_none(self):
        assert _store().get(99) is None

    def test_a_failure_carries_its_reason(self):
        store = _store()
        store.begin(1)

        store.set_status(1, Status.FAILED, Failure.INCORRECT_MFA)

        assert store.get(1) == link_state_store.LinkState(status=Status.FAILED, reason=Failure.INCORRECT_MFA)

    def test_an_unavailable_backend_does_not_fail_the_attempt(self):
        state = MagicMock()
        state.set.side_effect = StateBackendUnavailableError("down")

        link_state_store.GarminLinkStateStore(state=state).set_status(1, Status.COMPLETED)


def test_a_claim_is_not_left_behind_when_the_pending_state_cannot_be_written():
    state = MemoryState()
    store = link_state_store.GarminLinkStateStore(state=state)
    with (
        patch.object(state, "set", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(garmin_state_store.GarminStateUnavailableError),
    ):
        store.begin(1)

    assert store.begin(1) is True


def test_progress_renews_the_claim():
    state = MemoryState()
    store = link_state_store.GarminLinkStateStore(state=state, ttl_seconds=60)
    store.begin(1)
    with patch.object(state, "set") as write:
        store.set_status(1, Status.MFA_REQUIRED)

    assert garmin_state_store.key("link:claim", "1") in [call.args[0] for call in write.call_args_list]
