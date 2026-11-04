"""Tests for the outbound OIDC client: discovery, signing keys, credentials and userinfo."""

import json
import time
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from authlib.integrations.httpx_client import OAuth2Client
from fastapi import status
from jasil.providers import StateBackendUnavailableError

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

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expiry.pop(key, None)


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

    def test_refresh_skips_the_cache_and_replaces_it(self, service, state_provider):
        stale = {"keys": [{"kid": "old", "kty": "RSA"}]}
        fresh = {"keys": [{"kid": KID, "kty": "RSA"}]}
        state_provider.values[service._jwks_key(JWKS_URI)] = json.dumps(stale).encode()
        state_provider.expiry[service._jwks_key(JWKS_URI)] = time.monotonic() + 60
        client = self._client_returning(json_value=fresh)
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"),
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            assert service.fetch_jwks(JWKS_URI, refresh=True) == fresh
            assert service.fetch_jwks(JWKS_URI) == fresh
        client.get.assert_called_once()

    def test_the_guard_requires_tls(self, service):
        client = self._client_returning(json_value={"keys": []})
        with (
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url") as guard,
            patch.object(service, "http_client", MagicMock(return_value=client)),
        ):
            service.fetch_jwks(JWKS_URI)
        guard.assert_called_once_with(JWKS_URI, purpose="oidc_jwks", require_tls=True)

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


class TestDiscoveryIssuer:
    """OIDC Discovery 1.0 section 4.3: the document must name the issuer it was requested for."""

    GUARD = "modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"

    @staticmethod
    def _idp(issuer_url="https://idp.example.com"):
        idp = MagicMock(id=5, issuer_url=issuer_url)
        idp.name = "Test IdP"
        return idp

    @staticmethod
    def _client(document):
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value.json.return_value = document
        client.get.return_value.raise_for_status.return_value = None
        return client

    @pytest.mark.parametrize(
        ("configured", "advertised"),
        [
            ("https://idp.example.com", "https://idp.example.com"),
            ("https://idp.example.com/", "https://idp.example.com"),
            ("https://idp.example.com", "https://idp.example.com/"),
            ("https://idp.example.com/realm/", "https://idp.example.com/realm/"),
        ],
    )
    def test_a_matching_issuer_is_returned_and_cached(self, service, state_provider, configured, advertised):
        idp = self._idp(configured)
        document = {"issuer": advertised, "jwks_uri": JWKS_URI}
        with patch(self.GUARD), patch.object(service, "http_client", return_value=self._client(document)):
            assert service.get_oidc_configuration(idp) == document
        assert service._discovery_key(idp.id) in state_provider.values

    @pytest.mark.parametrize(
        "document", [{"issuer": "https://evil.example.com"}, {"jwks_uri": JWKS_URI}, {"issuer": 3}]
    )
    def test_a_different_or_missing_issuer_is_refused_and_not_cached(self, service, state_provider, document):
        idp = self._idp()
        with (
            patch(self.GUARD),
            patch.object(service, "http_client", return_value=self._client(document)),
            patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger,
        ):
            assert service.get_oidc_configuration(idp) is None
        assert service._discovery_key(idp.id) not in state_provider.values
        mock_logger.warning.assert_called_once()

    def test_a_cached_document_with_a_different_issuer_is_refused(self, service, state_provider):
        idp = self._idp()
        key = service._discovery_key(idp.id)
        state_provider.values[key] = json.dumps({"issuer": "https://evil.example.com"}).encode()
        state_provider.expiry[key] = time.monotonic() + 60
        with patch.object(service, "http_client") as http_client:
            assert service.get_oidc_configuration(idp) is None
        http_client.assert_not_called()

    def test_the_guard_requires_tls(self, service):
        document = {"issuer": "https://idp.example.com"}
        with patch(self.GUARD) as guard, patch.object(service, "http_client", return_value=self._client(document)):
            service.get_oidc_configuration(self._idp())
        guard.assert_called_once_with(
            "https://idp.example.com/.well-known/openid-configuration", purpose="oidc_discovery", require_tls=True
        )

    def test_a_document_that_is_not_json_is_refused_and_not_cached(self, service, state_provider):
        idp = self._idp()
        client = self._client(None)
        client.get.return_value.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
        with (
            patch(self.GUARD),
            patch.object(service, "http_client", return_value=client),
            patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger,
        ):
            assert service.get_oidc_configuration(idp) is None
        assert service._discovery_key(idp.id) not in state_provider.values
        assert "unreadable or issuer URL invalid" in mock_logger.warning.call_args.args[0]

    def test_an_issuer_url_httpx_cannot_send_to_is_refused(self, service):
        """A non-printable character passes the SSRF guard's parse but not httpx's."""
        idp = self._idp("https://idp.example.com/\x7frealm")
        with patch(self.GUARD), patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger:
            assert service.get_oidc_configuration(idp) is None
        assert isinstance(mock_logger.warning.call_args.kwargs["exc_info"], httpx2.InvalidURL)

    def test_an_unexpected_failure_propagates(self, service):
        client = self._client(None)
        client.get.side_effect = RuntimeError("bug")
        with (
            patch(self.GUARD),
            patch.object(service, "http_client", return_value=client),
            pytest.raises(RuntimeError, match="bug"),
        ):
            service.get_oidc_configuration(self._idp())


class TestResolveTokenEndpoint:
    @staticmethod
    def _idp(**overrides):
        values = {"id": 5, "issuer_url": "https://idp.example.com", "token_endpoint": None}
        values.update(overrides)
        idp = MagicMock(**values)
        idp.name = "Test IdP"
        return idp

    def test_the_discovered_endpoint_is_used_and_guarded(self, service):
        with (
            patch.object(
                service, "get_oidc_configuration", return_value={"token_endpoint": "https://idp.example.com/t"}
            ),
            patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url") as guard,
        ):
            assert service.resolve_token_endpoint(self._idp()) == "https://idp.example.com/t"
        guard.assert_called_once_with("https://idp.example.com/t", purpose="oidc_token", require_tls=True)

    def test_a_failed_discovery_is_refused_as_upstream(self, service):
        with (
            patch.object(service, "get_oidc_configuration", return_value=None),
            pytest.raises(core_exceptions.UpstreamError, match="token endpoint could not be resolved"),
        ):
            service.resolve_token_endpoint(self._idp())

    def test_an_unexpected_discovery_failure_propagates(self, service):
        with (
            patch.object(service, "get_oidc_configuration", side_effect=RuntimeError("bug")),
            pytest.raises(RuntimeError, match="bug"),
        ):
            service.resolve_token_endpoint(self._idp())


class TestForgetDiscovery:
    def test_it_deletes_the_cached_document(self, service, state_provider):
        key = service._discovery_key(9)
        state_provider.values[key] = b"{}"
        state_provider.expiry[key] = time.monotonic() + 60
        other = service._discovery_key(10)
        state_provider.values[other] = b"{}"

        service.forget_discovery(9)

        assert key not in state_provider.values
        assert other in state_provider.values

    def test_a_state_outage_is_logged_and_swallowed(self):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")
        service = oidc_client_service.OidcClientService(state, "test")
        with patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger:
            service.forget_discovery(9)
        mock_logger.warning.assert_called_once()


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

    @staticmethod
    def _client(claims):
        client = MagicMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = claims
        client.request = MagicMock(return_value=response)
        return client

    def _get(self, service, *, token_response, client=None, endpoint=None, jwks_uri=JWKS_URI, issuer=ISS, require):
        with patch("modules.auth.identity_providers.oidc_client_service.core_network.reject_private_url"):
            return service.get_userinfo(
                token_response=token_response,
                userinfo_endpoint=endpoint,
                client=client or MagicMock(),
                jwks_uri=jwks_uri,
                expected_issuer=issuer,
                expected_audience=AUD,
                require_id_token=require,
            )

    def test_userinfo_only_is_accepted_for_a_provider_without_id_tokens(self, service):
        client = self._client({"sub": "user-1", "email": "a@example.com"})
        result = self._get(
            service,
            token_response={"access_token": "at"},
            client=client,
            endpoint="https://idp.example.com/userinfo",
            jwks_uri=None,
            issuer=None,
            require=False,
        )
        assert result == {"sub": "user-1", "email": "a@example.com"}

    def test_id_token_claims_override_userinfo_on_merge(self, service):
        client = self._client({"sub": "verified-sub", "name": "From Endpoint", "email": "e@example.com"})
        verified = {"sub": "verified-sub", "email": "v@example.com"}
        with patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)):
            result = self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=True,
            )
        # ID-token claims take precedence; endpoint-only fields are preserved.
        assert result == {"sub": "verified-sub", "email": "v@example.com", "name": "From Endpoint"}

    @pytest.mark.parametrize("require", [True, False])
    def test_a_userinfo_subject_that_differs_from_the_id_token_subject_is_refused(self, service, require):
        client = self._client({"sub": "attacker-sub", "email": "a@example.com"})
        with (
            patch.object(
                oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value={"sub": "verified-sub"})
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=require,
            )

    def test_a_userinfo_without_a_subject_is_refused_when_an_id_token_is_merged(self, service):
        client = self._client({"email": "a@example.com"})
        with (
            patch.object(
                oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value={"sub": "verified-sub"})
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=True,
            )

    def test_id_token_only_returns_verified_claims(self, service):
        verified = {"sub": "verified-sub"}
        with patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)):
            result = self._get(service, token_response={"id_token": "idt"}, require=True)
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
            self._get(service, token_response={"id_token": "idt"}, require=True)
        assert exc_info.value.status_code == 401

    @pytest.mark.parametrize("jwks_uri, issuer", [(None, ISS), (JWKS_URI, None), (None, None)])
    def test_a_required_id_token_cannot_be_checked_without_issuer_and_keys(self, service, jwks_uri, issuer):
        """A forged userinfo response must not be accepted when the ID token cannot be verified."""
        client = self._client({"sub": "forged"})
        with pytest.raises(core_exceptions.UpstreamError):
            self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                jwks_uri=jwks_uri,
                issuer=issuer,
                require=True,
            )

    @pytest.mark.parametrize("token_response", [{"access_token": "at"}, {"access_token": "at", "id_token": None}])
    def test_a_required_id_token_that_is_missing_is_refused_despite_userinfo(self, service, token_response):
        client = self._client({"sub": "forged"})
        with pytest.raises(core_exceptions.UpstreamError):
            self._get(
                service,
                token_response=token_response,
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=True,
            )

    def test_nothing_to_return_fails_closed_with_500(self, service):
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            self._get(service, token_response={}, jwks_uri=None, issuer=None, require=False)
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.parametrize("token_extra", [{"expires_in": 30, "refresh_token": "rt"}, {"expires_in": 30}])
    def test_an_access_token_about_to_expire_still_fetches_userinfo(self, service, token_extra):
        """authlib counts a token expiring within its leeway as expired; the userinfo call must not depend on it."""
        seen: list[httpx2.Request] = []

        def provider(request: httpx2.Request) -> httpx2.Response:
            seen.append(request)
            if request.url.path == "/token":
                return httpx2.Response(200, json={"access_token": "at", "token_type": "Bearer", **token_extra})
            return httpx2.Response(200, json={"sub": "user-1", "email": "a@example.com"})

        client = OAuth2Client(client_id=AUD, client_secret="secret", transport=httpx2.MockTransport(provider))
        with client:
            token_response = client.fetch_token(
                "https://idp.example.com/token", grant_type="authorization_code", code="c"
            )
            result = self._get(
                service,
                token_response=token_response,
                client=client,
                endpoint="https://idp.example.com/userinfo",
                jwks_uri=None,
                issuer=None,
                require=False,
            )

        assert result == {"sub": "user-1", "email": "a@example.com"}
        assert [request.url.path for request in seen] == ["/token", "/userinfo"]
        assert seen[1].headers["Authorization"] == "Bearer at"

    @pytest.mark.parametrize(
        "error",
        [ValueError("not JSON"), httpx2.InvalidURL("non-printable character")],
        ids=lambda error: type(error).__name__,
    )
    def test_an_unreadable_userinfo_answer_falls_back_to_verified_id_token(self, service, error):
        client = MagicMock()
        client.request.return_value.raise_for_status.return_value = None
        client.request.return_value.json.side_effect = error
        verified = {"sub": "verified-sub"}
        with (
            patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)),
            patch("modules.auth.identity_providers.oidc_client_service.logger") as mock_logger,
        ):
            result = self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=True,
            )
        assert result == verified
        mock_logger.warning.assert_called_once()

    def test_an_unexpected_userinfo_failure_propagates(self, service):
        client = MagicMock()
        client.request.side_effect = RuntimeError("bug")
        with pytest.raises(RuntimeError, match="bug"):
            self._get(
                service,
                token_response={"access_token": "at"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                jwks_uri=None,
                issuer=None,
                require=False,
            )

    def test_endpoint_failure_falls_back_to_verified_id_token(self, service):
        """If the userinfo endpoint errors, a verified ID token is still the identity."""
        client = MagicMock()
        client.request = MagicMock(side_effect=httpx2.RequestError("network down"))
        verified = {"sub": "verified-sub"}
        with patch.object(oidc_client_service.id_token_service, "verify_id_token", MagicMock(return_value=verified)):
            result = self._get(
                service,
                token_response={"access_token": "at", "id_token": "idt"},
                client=client,
                endpoint="https://idp.example.com/userinfo",
                require=True,
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
