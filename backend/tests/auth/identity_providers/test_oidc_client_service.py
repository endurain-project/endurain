"""Tests for the outbound OIDC client: discovery, signing keys, credentials and userinfo."""

import json
import time
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from fastapi import status

import core.exceptions as core_exceptions
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

KID = "test-key-1"
ISS = "https://idp.example.com"
AUD = "client-id-123"
JWKS_URI = "https://idp.example.com/jwks"


class _MemoryState:
    def __init__(self):
        self.values: dict[str, bytes] = {}
        self.expiry: dict[str, float] = {}

    def get(self, key: str) -> bytes | None:
        if self.expiry.get(key, 0) <= time.monotonic():
            self.values.pop(key, None)
            self.expiry.pop(key, None)
        return self.values.get(key)

    def set(self, key: str, value: bytes, *, ttl_seconds: int) -> None:
        self.values[key] = value
        self.expiry[key] = time.monotonic() + ttl_seconds


@pytest.fixture
def state_provider() -> _MemoryState:
    return _MemoryState()


@pytest.fixture
def service(state_provider) -> oidc_client_service.OidcClientService:
    """Return a fresh service instance backed by shared test state."""
    return oidc_client_service.OidcClientService(state_provider, "test")


# ---------------------------------------------------------------------------
# _fetch_jwks
# ---------------------------------------------------------------------------


class TestFetchJwks:
    """JWKS retrieval: caching, SSRF guard, and error mapping."""

    def _client_returning(self, *, json_value=None, raise_for_status_exc=None, get_exc=None) -> MagicMock:
        """Build a mock HTTP client context with a single GET behaviour."""
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        if get_exc is not None:
            client.get = MagicMock(side_effect=get_exc)
            return client
        response = MagicMock()
        if raise_for_status_exc is not None:
            response.raise_for_status.side_effect = raise_for_status_exc
        else:
            response.raise_for_status.return_value = None
        response.json.return_value = json_value
        client.get = MagicMock(return_value=response)
        return client

    def test_cache_hit_returns_without_network(self, service, state_provider):
        cached = {"keys": [{"kid": KID, "kty": "RSA"}]}
        state_provider.values[service._jwks_key(JWKS_URI)] = json.dumps(cached).encode()
        state_provider.expiry[service._jwks_key(JWKS_URI)] = time.monotonic() + 60
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client") as mock_client,
        ):
            result = service.fetch_jwks(JWKS_URI)
        assert result == cached
        mock_client.assert_not_called()

    def test_successful_fetch_caches_result(self, service):
        jwks = {"keys": [{"kid": KID, "kty": "RSA"}]}
        client = self._client_returning(json_value=jwks)
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            result = service.fetch_jwks(JWKS_URI)
            assert result == jwks
            assert service._jwks_key(JWKS_URI) in service._state.values

    def test_invalid_structure_is_rejected(self, service):
        client = self._client_returning(json_value={"no_keys": True})
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service.fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    def test_timeout_raises_504(self, service):
        client = self._client_returning(get_exc=httpx2.TimeoutException("timeout"))
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service.fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    def test_http_status_error_raises_502(self, service):
        err = httpx2.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        client = self._client_returning(raise_for_status_exc=err)
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service.fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    def test_ssrf_guard_blocks_before_any_fetch(self, service):
        """A private/internal JWKS URL must be blocked before any HTTP call.

        The SSRF guard fires before ``_get_http_client``/``client.get``, and its
        status is preserved for the caller.
        """
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url",
                side_effect=core_exceptions.InvalidInputError("blocked"),
            ),
            patch.object(service, "http_client", MagicMock()) as mock_client,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.fetch_jwks("http://169.254.169.254/jwks")
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_client.assert_not_called()


class TestGetOidcConfigurationGuardFailures:
    """Discovery logs why the SSRF guard did not clear the issuer URL."""

    def test_blocked_url_points_the_operator_at_ssrf_allowed_hosts(self, service):
        idp = MagicMock(issuer_url="https://idp.example.com", id=1)
        idp.name = "Test IdP"
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url",
                side_effect=core_exceptions.InvalidInputError("URL resolves to a non-public address"),
            ),
            patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger,
        ):
            result = service.get_oidc_configuration(idp)

        message = str(mock_logger.warning.call_args)
        assert result is None
        assert "was rejected" in message
        assert "SSRF_ALLOWED_HOSTS" in message


def test_discovery_cache_is_shared_between_services_and_refetches_after_expiry(state_provider):
    idp = MagicMock(id=23, name="Test IdP", issuer_url="https://idp.example.com")
    document = {"issuer": idp.issuer_url, "jwks_uri": JWKS_URI}

    def client_with_document():
        client = MagicMock()
        client.__enter__.return_value = client
        response = MagicMock()
        response.json.return_value = document
        response.raise_for_status.return_value = None
        client.get.return_value = response
        return client

    first = oidc_client_service.OidcClientService(state_provider, "test")
    second = oidc_client_service.OidcClientService(state_provider, "test")
    first_client = client_with_document()
    with (
        patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
        patch.object(first, "http_client", return_value=first_client),
    ):
        assert first.get_oidc_configuration(idp) == document
    first_client.get.assert_called_once()

    with patch.object(second, "http_client") as second_client:
        assert second.get_oidc_configuration(idp) == document
    second_client.assert_not_called()

    key = first._discovery_key(idp.id)
    state_provider.expiry[key] = time.monotonic() - 1
    expired_client = client_with_document()
    with (
        patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
        patch.object(second, "http_client", return_value=expired_client),
    ):
        assert second.get_oidc_configuration(idp) == document
    expired_client.get.assert_called_once()


# ---------------------------------------------------------------------------
# _get_userinfo
# ---------------------------------------------------------------------------


class TestGetUserinfo:
    """Orchestration of userinfo endpoint and verified ID-token claims."""

    def test_userinfo_endpoint_only_returns_claims(self, service):
        client = MagicMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sub": "user-1", "email": "a@example.com"}
        client.get = MagicMock(return_value=response)
        with patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"):
            result = service.get_userinfo(
                token_response={"access_token": "at"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=None,
                expected_issuer=None,
                expected_audience=AUD,
            )
        assert result == {"sub": "user-1", "email": "a@example.com"}

    def test_id_token_claims_override_userinfo_on_merge(self, service):
        client = MagicMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sub": "endpoint-sub", "name": "From Endpoint"}
        client.get = MagicMock(return_value=response)
        verified = {"sub": "verified-sub", "email": "v@example.com"}
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)),
        ):
            result = service.get_userinfo(
                token_response={"access_token": "at", "id_token": "idt"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        # ID-token claims take precedence; endpoint-only fields are preserved.
        assert result["sub"] == "verified-sub"
        assert result["email"] == "v@example.com"
        assert result["name"] == "From Endpoint"

    def test_id_token_only_returns_verified_claims(self, service):
        verified = {"sub": "verified-sub"}
        with patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)):
            result = service.get_userinfo(
                token_response={"id_token": "idt"},
                userinfo_endpoint=None,
                client=MagicMock(),
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert result == verified

    def test_id_token_verification_failure_is_reraised(self, service):
        with (
            patch.object(
                oidc_client_service.id_token_service,
                "verify_id_token",
                MagicMock(side_effect=core_exceptions.UnauthenticatedError("bad signature")),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.get_userinfo(
                token_response={"id_token": "idt"},
                userinfo_endpoint=None,
                client=MagicMock(),
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert exc_info.value.status_code == 401

    def test_no_userinfo_and_no_verifiable_id_token_raises_500(self, service):
        """Nothing to return → fail closed with 500."""
        result_client = MagicMock()
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.get_userinfo(
                token_response={},
                userinfo_endpoint=None,
                client=result_client,
                jwks_uri=None,
                expected_issuer=None,
                expected_audience=AUD,
            )
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_endpoint_failure_falls_back_to_verified_id_token(self, service):
        """If the userinfo endpoint errors, a verified ID token still wins."""
        client = MagicMock()
        client.get = MagicMock(side_effect=httpx2.RequestError("network down"))
        verified = {"sub": "verified-sub"}
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)),
        ):
            result = service.get_userinfo(
                token_response={"access_token": "at", "id_token": "idt"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert result == verified


class TestDecryptClientId:
    """decrypt_client_id fails closed on decryption problems."""

    def test_returns_decrypted_value(self, service):
        idp = MagicMock()
        idp.client_id = "encrypted-id"
        with patch(
            "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
            return_value="plain-client-id",
        ):
            assert service.decrypt_client_id(idp) == "plain-client-id"

    def test_empty_decryption_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_id = "encrypted-id"
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
                return_value="",
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.decrypt_client_id(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_decryption_exception_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_id = "encrypted-id"
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
                side_effect=ValueError("bad token"),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.decrypt_client_id(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDecryptClientSecret:
    """decrypt_client_secret fails closed on decryption problems."""

    def test_returns_decrypted_value(self, service):
        idp = MagicMock()
        idp.client_secret = "encrypted-secret"
        with patch(
            "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
            return_value="plain-secret",
        ):
            assert service.decrypt_client_secret(idp) == "plain-secret"

    def test_empty_decryption_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_secret = "encrypted-secret"
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
                return_value="",
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.decrypt_client_secret(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_decryption_exception_raises_500(self, service):
        idp = MagicMock()
        idp.name = "TestIdP"
        idp.client_secret = "encrypted-secret"
        with (
            patch(
                "modules.auth.identity_providers.oidc_client_service.core_cryptography.decrypt_token_fernet",
                side_effect=ValueError("bad token"),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service.decrypt_client_secret(idp)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDiscoveryErrorLogging:
    """An IdP error body is never written to the log."""

    def test_http_status_error_logs_status_code_only(self):
        service = oidc_client_service.OidcClientService(MagicMock(), "test")
        idp = MagicMock()
        idp.id = 1
        idp.name = "TestIdP"
        idp.issuer_url = "https://idp.example"
        response = MagicMock(status_code=500, text="secret-body")
        client = MagicMock()
        client.__enter__.return_value.get.return_value.raise_for_status.side_effect = httpx2.HTTPStatusError(
            "boom", request=MagicMock(), response=response
        )
        with (
            patch.object(service, "_read_cache", return_value=None),
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
            patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger,
        ):
            assert service.get_oidc_configuration(idp) is None

        extra = mock_logger.warning.call_args.kwargs["extra"]
        assert extra["status_code"] == 500
        assert "secret-body" not in str(extra)


class TestNoRedirects:
    """A redirect would send the request, and any secret it carries, to a host the SSRF check never saw."""

    def test_the_plain_client_never_follows_a_redirect(self):
        service = oidc_client_service.OidcClientService(MagicMock(), "v1")

        with service.http_client() as client:
            assert client.follow_redirects is False

    def test_the_oauth_client_never_follows_a_redirect(self):
        service = oidc_client_service.OidcClientService(MagicMock(), "v1")

        client = service.create_oauth_client("id", "secret", None)

        assert client.follow_redirects is False
        assert client.code_challenge_method == "S256"
        client.close()
