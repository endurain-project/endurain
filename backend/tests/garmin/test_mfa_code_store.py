"""Tests for garmin.mfa_code_store (provider-backed)."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.state_store as garmin_state_store


class TestGarminMFACodeStore:
    """GarminMFACodeStore backed by the platform StateProvider."""

    def _make_store(self) -> mfa_code_store.GarminMFACodeStore:
        return mfa_code_store.GarminMFACodeStore(state=MemoryState())

    def test_add_code_stores_it(self):
        store = self._make_store()
        store.add_code(1, "123456")
        assert store.get_code(1) == "123456"

    def test_get_code_returns_value(self):
        store = self._make_store()
        store.add_code(2, "654321")
        assert store.get_code(2) == "654321"

    def test_get_code_missing_returns_none(self):
        assert self._make_store().get_code(99) is None

    def test_delete_code_removes_entry(self):
        store = self._make_store()
        store.add_code(3, "abc")
        store.delete_code(3)
        assert store.get_code(3) is None

    def test_delete_code_missing_is_noop(self):
        self._make_store().delete_code(99)

    def test_overwrite_code_updates_value(self):
        store = self._make_store()
        store.add_code(7, "old")
        store.add_code(7, "new")
        assert store.get_code(7) == "new"

    def test_distinct_users_isolated(self):
        store = self._make_store()
        store.add_code(1, "aaa")
        store.add_code(2, "bbb")
        assert store.get_code(1) == "aaa"
        assert store.get_code(2) == "bbb"


class TestGarminMFACodeStoreUnavailable:
    """Backend outages surface as GarminStateUnavailableError; delete swallows."""

    def _failing_store(self) -> mfa_code_store.GarminMFACodeStore:
        state = MagicMock()
        for method in ("set", "get", "delete", "delete_prefix"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        return mfa_code_store.GarminMFACodeStore(state=state)

    def test_add_code_raises_unavailable(self):
        with pytest.raises(garmin_state_store.GarminStateUnavailableError):
            self._failing_store().add_code(1, "x")

    def test_get_code_raises_unavailable(self):
        with pytest.raises(garmin_state_store.GarminStateUnavailableError):
            self._failing_store().get_code(1)

    def test_delete_code_swallows_outage(self):
        # delete_code is best-effort (entries expire via TTL), so an outage must not raise.
        self._failing_store().delete_code(1)
