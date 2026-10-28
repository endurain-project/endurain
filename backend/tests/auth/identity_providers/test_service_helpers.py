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

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

import core.exceptions as core_exceptions
from modules.auth.identity_providers.service import IdentityProviderService, TokenAction


@pytest.fixture
def service() -> IdentityProviderService:
    """Return a fresh service instance with empty caches."""
    return IdentityProviderService(MagicMock(), "https://endurain.example", "test")


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
            pytest.raises(core_exceptions.DomainError) as exc_info,
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
            pytest.raises(core_exceptions.DomainError) as exc_info,
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
            pytest.raises(core_exceptions.DomainError) as exc_info,
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
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._decrypt_client_secret(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


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
        import modules.auth.identity_providers.integration_service as idp_integration

        db = MagicMock()
        provider = MagicMock()
        with patch.object(
            idp_integration.identity_providers_crud, "get_identity_provider", return_value=provider
        ) as get:
            result = idp_integration.get_identity_provider(7, db)
        get.assert_called_once_with(7, db)
        assert result is provider
