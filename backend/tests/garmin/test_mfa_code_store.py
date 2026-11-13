"""Tests for garmin.mfa_code_store (provider-backed)."""

import uuid
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import modules.garmin.mfa_code_store as mfa_code_store
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID


class TestGarminMFACodeStore:
    """GarminMFACodeStore backed by the platform StateProvider."""

    def _make_store(self) -> mfa_code_store.GarminMFACodeStore:
        return mfa_code_store.GarminMFACodeStore(state=MemoryState())

    def test_add_code_stores_it(self):
        store = self._make_store()
        store.add_code(MOCK_USER_ID, "123456")
        assert store.get_code(MOCK_USER_ID) == "123456"

    def test_get_code_returns_value(self):
        store = self._make_store()
        store.add_code(OTHER_USER_ID, "654321")
        assert store.get_code(OTHER_USER_ID) == "654321"

    def test_get_code_missing_returns_none(self):
        assert self._make_store().get_code(uuid.UUID(int=99)) is None

    def test_delete_code_removes_entry(self):
        store = self._make_store()
        store.add_code(uuid.UUID(int=3), "abc")
        store.delete_code(uuid.UUID(int=3))
        assert store.get_code(uuid.UUID(int=3)) is None

    def test_delete_code_missing_is_noop(self):
        self._make_store().delete_code(uuid.UUID(int=99))

    def test_overwrite_code_updates_value(self):
        store = self._make_store()
        store.add_code(MOCK_USER_ID, "old")
        store.add_code(MOCK_USER_ID, "new")
        assert store.get_code(MOCK_USER_ID) == "new"

    def test_distinct_users_isolated(self):
        store = self._make_store()
        store.add_code(MOCK_USER_ID, "aaa")
        store.add_code(OTHER_USER_ID, "bbb")
        assert store.get_code(MOCK_USER_ID) == "aaa"
        assert store.get_code(OTHER_USER_ID) == "bbb"


class TestGarminMFACodeStoreUnavailable:
    """Backend outages surface as StateUnavailableError; delete swallows."""

    def _failing_store(self) -> mfa_code_store.GarminMFACodeStore:
        state = MagicMock()
        for method in ("set", "get", "delete", "delete_prefix"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        return mfa_code_store.GarminMFACodeStore(state=state)

    def test_add_code_raises_unavailable(self):
        with pytest.raises(core_attempt_state.StateUnavailableError):
            self._failing_store().add_code(MOCK_USER_ID, "x")

    def test_get_code_raises_unavailable(self):
        with pytest.raises(core_attempt_state.StateUnavailableError):
            self._failing_store().get_code(MOCK_USER_ID)

    def test_delete_code_swallows_outage(self):
        # delete_code is best-effort (entries expire via TTL), so an outage must not raise.
        self._failing_store().delete_code(MOCK_USER_ID)


def test_the_code_is_not_stored_in_plaintext():
    state = MemoryState()
    mfa_code_store.GarminMFACodeStore(state=state).add_code(MOCK_USER_ID, "123456")

    stored = state.get(core_attempt_state.key("garmin", "mfa:code", str(MOCK_USER_ID)))

    assert stored is not None
    assert b"123456" not in stored
