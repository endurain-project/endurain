"""Tests for temporary MFA setup secret storage (provider-backed)."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.auth.mfa.setup_store as auth_mfa_setup_store


class TestMFASecretStore:
    """MFASecretStore backed by the platform StateProvider."""

    def _make_store(self, ttl: int = 300) -> auth_mfa_setup_store.MFASecretStore:
        return auth_mfa_setup_store.MFASecretStore(state=MemoryState(), ttl_seconds=ttl)

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
        store.add_secret(1, "old")
        store.add_secret(1, "new")
        assert store.get_secret(1) == "new"

    def test_add_secret_encryption_failure(self):
        with (
            patch("modules.auth.mfa.setup_store.core_cryptography.encrypt_token_fernet", return_value=None),
            pytest.raises(ValueError, match="Failed to encrypt MFA secret"),
        ):
            self._make_store().add_secret(123, "secret-value")

    def test_get_secret_returns_none_when_decrypt_fails(self):
        store = self._make_store()
        store.add_secret(1, "secret")
        with patch("modules.auth.mfa.setup_store.core_cryptography.decrypt_token_fernet", side_effect=Exception("bad")):
            assert store.get_secret(1) is None


class TestEncryptionHelpers:
    """Direct tests for the module-level encryption helpers."""

    def test_encrypt_secret_error(self):
        with (
            patch("modules.auth.mfa.setup_store.core_cryptography.encrypt_token_fernet", return_value=None),
            pytest.raises(ValueError, match="Failed to encrypt MFA secret"),
        ):
            auth_mfa_setup_store._encrypt_secret("test-secret")

    def test_decrypt_secret_returns_none_on_error(self):
        with patch(
            "modules.auth.mfa.setup_store.core_cryptography.decrypt_token_fernet", side_effect=Exception("bad decrypt")
        ):
            assert auth_mfa_setup_store._decrypt_secret("bad-encrypted-data", 123) is None


class TestMFASecretStoreUnavailable:
    """Backend outages surface as MFASecretStoreUnavailableError; delete swallows."""

    def _failing_store(self) -> auth_mfa_setup_store.MFASecretStore:
        state = MagicMock()
        for method in ("set", "get", "delete", "delete_prefix"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        return auth_mfa_setup_store.MFASecretStore(state=state)

    def test_add_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().add_secret(1, "secret-value")

    def test_get_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().get_secret(1)

    def test_has_secret_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().has_secret(1)

    def test_clear_all_raises_unavailable(self):
        with pytest.raises(auth_mfa_setup_store.MFASecretStoreUnavailableError):
            self._failing_store().clear_all()

    def test_delete_secret_swallows_outage(self):
        self._failing_store().delete_secret(1)


class TestGetMFASecretStore:
    """get_mfa_secret_store: returns the module singleton."""

    def test_returns_singleton(self):
        assert auth_mfa_setup_store.get_mfa_secret_store() is auth_mfa_setup_store.mfa_secret_store
