"""Tests for testable pure helpers on IdentityProviderService.

The IdP OAuth2/OIDC service is large and mostly network-bound; its
account-takeover gate (``_find_or_create_user`` / ``_is_email_verified``) is
covered in ``test_service_find_or_create_user.py``. This module adds coverage
for the remaining synchronous, security-relevant helpers that do not require
mocking HTTP flows:

- ``_map_user_claims`` — claim-to-user-field mapping and custom overrides.
- ``_get_redirect_uri`` — callback URL construction.
- ``_decrypt_client_id`` / ``_decrypt_client_secret`` — Fernet decryption with
  fail-closed error handling (500 on decrypt failure / empty result).
- ``_prune_expired_caches`` — bounded in-memory cache eviction.
- ``TokenAction`` — token-rotation policy enum values.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from modules.auth.identity_providers.service import IdentityProviderService, TokenAction


@pytest.fixture
def service() -> IdentityProviderService:
    """Return a fresh service instance with empty caches."""
    return IdentityProviderService()


class TestMapUserClaims:
    """_map_user_claims maps IdP claims to standard user fields."""

    def _idp(self, user_mapping=None) -> MagicMock:
        idp = MagicMock()
        idp.user_mapping = user_mapping
        return idp

    def test_default_mapping_prefers_preferred_username(self, service):
        claims = {
            "preferred_username": "alice",
            "email": "alice@example.com",
            "name": "Alice Example",
        }
        result = service._map_user_claims(self._idp(), claims)
        assert result["username"] == "alice"
        assert result["email"] == "alice@example.com"
        assert result["name"] == "Alice Example"

    def test_username_falls_back_through_claim_list(self, service):
        """With no preferred_username/username, it falls back to email then sub."""
        claims = {"email": "bob@example.com", "sub": "subject-123"}
        result = service._map_user_claims(self._idp(), claims)
        assert result["username"] == "bob@example.com"

    def test_username_falls_back_to_sub_when_no_email(self, service):
        claims = {"sub": "subject-123"}
        result = service._map_user_claims(self._idp(), claims)
        assert result["username"] == "subject-123"

    def test_custom_mapping_overrides_default(self, service):
        idp = self._idp(user_mapping={"username": ["custom_login"]})
        claims = {"custom_login": "custom-user", "preferred_username": "ignored"}
        result = service._map_user_claims(idp, claims)
        assert result["username"] == "custom-user"

    def test_custom_mapping_accepts_string_value(self, service):
        """A custom mapping given as a bare string is treated as a single claim."""
        idp = self._idp(user_mapping={"username": "single_claim"})
        claims = {"single_claim": "value-x"}
        result = service._map_user_claims(idp, claims)
        assert result["username"] == "value-x"

    def test_missing_claims_are_omitted(self, service):
        result = service._map_user_claims(self._idp(), {})
        assert result == {}

    def test_empty_claim_values_are_skipped(self, service):
        """Falsy claim values are skipped so the next candidate wins."""
        claims = {"preferred_username": "", "username": "", "email": "real@example.com"}
        result = service._map_user_claims(self._idp(), claims)
        assert result["username"] == "real@example.com"


class TestGetRedirectUri:
    """_get_redirect_uri builds the public callback URL."""

    def test_builds_expected_callback_url(self, service):
        mock_settings = MagicMock()
        mock_settings.ENDURAIN_HOST = "https://endurain.example"
        with patch("modules.auth.identity_providers.service.core_config.settings", mock_settings):
            uri = service._get_redirect_uri("my-idp")
        assert uri == "https://endurain.example/api/v1/public/idp/callback/my-idp"


class TestDecryptClientId:
    """_decrypt_client_id fails closed on decryption problems."""

    def test_returns_decrypted_value(self, service):
        idp = MagicMock()
        idp.client_id = "encrypted-id"
        with patch(
            "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
            return_value="plain-client-id",
        ):
            assert service._decrypt_client_id(idp) == "plain-client-id"

    def test_empty_decryption_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_id = "encrypted-id"
        with (
            patch(
                "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
                return_value="",
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service._decrypt_client_id(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_decryption_exception_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_id = "encrypted-id"
        with (
            patch(
                "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
                side_effect=ValueError("bad token"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service._decrypt_client_id(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDecryptClientSecret:
    """_decrypt_client_secret fails closed on decryption problems."""

    def test_returns_decrypted_value(self, service):
        idp = MagicMock()
        idp.client_secret = "encrypted-secret"
        with patch(
            "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
            return_value="plain-secret",
        ):
            assert service._decrypt_client_secret(idp) == "plain-secret"

    def test_empty_decryption_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_secret = "encrypted-secret"
        with (
            patch(
                "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
                return_value="",
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service._decrypt_client_secret(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_decryption_exception_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_secret = "encrypted-secret"
        with (
            patch(
                "modules.auth.identity_providers.service.core_cryptography.decrypt_token_fernet",
                side_effect=ValueError("bad token"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service._decrypt_client_secret(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestPruneExpiredCaches:
    """_prune_expired_caches evicts only stale entries."""

    def test_evicts_expired_discovery_entries(self, service):
        now = datetime.now(UTC)
        service._discovery_cache = {1: {"x": 1}, 2: {"y": 2}}
        service._cache_expiry = {
            1: now - timedelta(minutes=1),  # expired
            2: now + timedelta(hours=1),  # valid
        }
        service._prune_expired_caches()
        assert 1 not in service._discovery_cache
        assert 1 not in service._cache_expiry
        assert 2 in service._discovery_cache

    def test_evicts_expired_jwks_entries(self, service):
        now = datetime.now(UTC)
        service._jwks_cache = {
            "stale": {"jwks": {}, "cached_at": now - service._cache_ttl - timedelta(seconds=1)},
            "fresh": {"jwks": {}, "cached_at": now},
        }
        service._prune_expired_caches()
        assert "stale" not in service._jwks_cache
        assert "fresh" in service._jwks_cache

    def test_evicts_jwks_entry_missing_cached_at(self, service):
        service._jwks_cache = {"no-timestamp": {"jwks": {}, "cached_at": None}}
        service._prune_expired_caches()
        assert "no-timestamp" not in service._jwks_cache

    def test_keeps_all_when_nothing_expired(self, service):
        now = datetime.now(UTC)
        service._discovery_cache = {1: {"x": 1}}
        service._cache_expiry = {1: now + timedelta(hours=1)}
        service._jwks_cache = {"fresh": {"jwks": {}, "cached_at": now}}
        service._prune_expired_caches()
        assert service._discovery_cache == {1: {"x": 1}}
        assert "fresh" in service._jwks_cache


class TestTokenActionEnum:
    """TokenAction enum values used by token-rotation policy."""

    def test_enum_values(self):
        assert TokenAction.SKIP.value == "skip"
        assert TokenAction.REFRESH.value == "refresh"
        assert TokenAction.CLEAR.value == "clear"


class TestBoundaryFacades:
    """Module-level facades let the non-auth browser IdP-link router reach auth
    data operations without importing the auth CRUD layer directly (auth-boundary)."""

    def test_get_identity_provider_delegates_to_crud(self):
        import modules.auth.identity_providers.service as idp_service

        db = MagicMock()
        provider = MagicMock()
        with patch.object(idp_service.idp_crud, "get_identity_provider", return_value=provider) as get:
            result = idp_service.get_identity_provider(7, db)
        get.assert_called_once_with(7, db)
        assert result is provider

    def test_create_link_oauth_state_delegates_to_crud(self):
        import modules.auth.identity_providers.service as idp_service

        db = MagicMock()
        with patch.object(idp_service.oauth_state_crud, "create_oauth_state") as create:
            idp_service.create_link_oauth_state(
                db,
                state_id="state-id",
                idp_id=3,
                nonce="nonce",
                client_type="web",
                ip_address="203.0.113.1",
                user_id=42,
                redirect_path="/settings/security",
            )
        create.assert_called_once_with(
            db=db,
            state_id="state-id",
            idp_id=3,
            nonce="nonce",
            client_type="web",
            ip_address="203.0.113.1",
            user_id=42,
            redirect_path="/settings/security",
        )
