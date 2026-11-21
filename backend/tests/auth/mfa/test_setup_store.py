"""Tests for temporary MFA setup secret storage (provider-backed)."""

import pytest
from jasil.backends.state_memory import MemoryState

import modules.auth.mfa.setup_store as auth_mfa_setup_store
from tests._factories.state import DownState
from tests._helpers.auth import MOCK_USER_ID


class TestMFASecretStore:
    """MFASecretStore backed by the platform StateProvider."""

    def _make_store(self) -> auth_mfa_setup_store.MFASecretStore:
        return auth_mfa_setup_store.MFASecretStore(state=MemoryState())

    def test_lifecycle(self):
        store = self._make_store()
        store.add_secret(123, "secret-value")
        assert store.get_secret(123) == "secret-value"
        assert store.has_secret(123) is True
        store.delete_secret(123)
        assert store.get_secret(123) is None
        assert store.has_secret(123) is False

    def test_stored_value_is_encrypted(self):
        state = MemoryState()
        store = auth_mfa_setup_store.MFASecretStore(state=state)
        store.add_secret(123, "secret-value")
        raw = state.get(store._key(123))
        assert raw is not None
        assert b"secret-value" not in raw

    def test_missing_secret_returns_none(self):
        assert self._make_store().get_secret(999) is None
        assert self._make_store().has_secret(999) is False

    def test_clear_all(self):
        store = self._make_store()
        store.add_secret(123, "a")
        store.add_secret(456, "b")
        store.clear_all()
        assert store.has_secret(123) is False
        assert store.has_secret(456) is False

    def test_overwrite_updates_value(self):
        store = self._make_store()
        store.add_secret(MOCK_USER_ID, "old")
        store.add_secret(MOCK_USER_ID, "new")
        assert store.get_secret(MOCK_USER_ID) == "new"


class TestMFASecretStoreUnavailable:
    """Backend outages surface as MFASecretStoreUnavailableError; delete swallows."""

    def _failing_store(self) -> auth_mfa_setup_store.MFASecretStore:
        return auth_mfa_setup_store.MFASecretStore(state=DownState())

    def test_add_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().add_secret(MOCK_USER_ID, "secret-value")

    def test_get_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().get_secret(MOCK_USER_ID)

    def test_has_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().has_secret(MOCK_USER_ID)

    def test_clear_all_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().clear_all()

    def test_delete_secret_swallows_outage(self):
        self._failing_store().delete_secret(MOCK_USER_ID)


class TestDecryptSecretFailure:
    """A secret that cannot be decrypted is reported and treated as absent."""

    def test_undecryptable_secret_logs_a_warning_without_the_value_and_returns_none(self, caplog):
        state = MemoryState()
        store = auth_mfa_setup_store.MFASecretStore(state=state)
        state.set(store._key(MOCK_USER_ID), b"not-a-fernet-token", ttl_seconds=60)

        with caplog.at_level("WARNING"):
            assert store.get_secret(MOCK_USER_ID) is None

        assert len(caplog.records) == 1
        assert caplog.records[0].exc_info is not None
        assert "not-a-fernet-token" not in caplog.text
