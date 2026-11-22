"""Tests for COROS OAuth discovery, registration and token handling."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from urllib.parse import parse_qs

import httpx2
import pytest

import core.exceptions as core_exceptions
import modules.coros.contracts as contracts
import modules.coros.oauth as oauth


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _metadata() -> contracts.CorosOAuthMetadata:
    return contracts.CorosOAuthMetadata(
        issuer="https://mcpeu.coros.com",
        authorization_endpoint="https://mcpeu.coros.com/oauth2/authorize",
        token_endpoint="https://mcpeu.coros.com/oauth2/token",
        revocation_endpoint="https://mcpeu.coros.com/oauth2/revoke",
        registration_endpoint="https://mcpeu.coros.com/connect/register",
        mcp_url="https://mcpeu.coros.com/mcp",
        scopes=("openid", "offline_access", "mcp.tools"),
    )


class TestPkce:
    """PKCE values must match the S256 specification."""

    def test_challenge_is_the_base64url_sha256_of_the_verifier(self):
        verifier, challenge = oauth.generate_pkce_pair()

        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        assert challenge == expected
        assert 43 <= len(verifier) <= 128

    def test_state_is_unique(self):
        assert oauth.generate_state() != oauth.generate_state()


class TestDiscovery:
    """Discovery follows the gateway's published metadata."""

    def test_oidc_document_selects_the_regional_issuer_and_resource(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path == "/.well-known/openid-configuration":
                return httpx2.Response(
                    200,
                    json={
                        "issuer": "https://mcpeu.coros.com",
                        "authorization_endpoint": "https://mcpeu.coros.com/oauth2/authorize",
                        "token_endpoint": "https://mcpeu.coros.com/oauth2/token",
                        "revocation_endpoint": "https://mcpeu.coros.com/oauth2/revoke",
                        "registration_endpoint": "https://mcpeu.coros.com/connect/register",
                        "scopes_supported": ["openid", "mcp.tools", "offline_access"],
                    },
                )
            if request.url.path == "/.well-known/oauth-protected-resource/mcp":
                return httpx2.Response(200, json={"resource": "https://mcpeu.coros.com/mcp"})
            return httpx2.Response(404)

        metadata = oauth.discover_metadata(_client(handler))

        assert metadata.issuer == "https://mcpeu.coros.com"
        assert metadata.mcp_url == "https://mcpeu.coros.com/mcp"
        assert metadata.scopes == ("openid", "mcp.tools", "offline_access")

    def test_protected_resource_fallback_is_used_when_oidc_is_missing(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path == "/.well-known/openid-configuration":
                return httpx2.Response(404)
            if request.url.path == "/mcp":
                return httpx2.Response(
                    401,
                    headers={
                        "www-authenticate": (
                            'Bearer resource_metadata="https://mcpeu.coros.com/'
                            '.well-known/oauth-protected-resource/mcp"'
                        )
                    },
                )
            if request.url.path == "/.well-known/oauth-protected-resource/mcp":
                return httpx2.Response(
                    200,
                    json={
                        "resource": "https://mcpeu.coros.com/mcp",
                        "authorization_servers": ["https://mcpeu.coros.com"],
                    },
                )
            if request.url.path == "/.well-known/oauth-authorization-server":
                return httpx2.Response(
                    200,
                    json={
                        "issuer": "https://mcpeu.coros.com",
                        "authorization_endpoint": "https://mcpeu.coros.com/oauth2/authorize",
                        "token_endpoint": "https://mcpeu.coros.com/oauth2/token",
                        "scopes_supported": ["openid", "mcp.tools", "offline_access"],
                    },
                )
            return httpx2.Response(404)

        metadata = oauth.discover_metadata(_client(handler))

        assert metadata.issuer == "https://mcpeu.coros.com"
        assert metadata.registration_endpoint is None

    def test_an_untrusted_issuer_is_rejected(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            if request.url.path == "/.well-known/openid-configuration":
                return httpx2.Response(
                    200,
                    json={
                        "issuer": "https://evil.example",
                        "authorization_endpoint": "https://evil.example/authorize",
                        "token_endpoint": "https://evil.example/token",
                    },
                )
            return httpx2.Response(404)

        with pytest.raises(oauth.CorosProtocolError):
            oauth.discover_metadata(_client(handler))

    def test_transport_failures_are_transient(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("down", request=request)

        with pytest.raises(oauth.CorosTransientError):
            oauth.discover_metadata(_client(handler))

    def test_a_rate_limited_discovery_is_not_treated_as_missing_metadata(self):
        requested: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requested.append(request.url.path)
            if request.url.path == "/.well-known/openid-configuration":
                return httpx2.Response(429, headers={"retry-after": "60"})
            return httpx2.Response(404)

        with pytest.raises(core_exceptions.TooManyRequestsError) as caught:
            oauth.discover_metadata(_client(handler))

        assert caught.value.retry_at is not None
        assert requested == ["/.well-known/openid-configuration"]


class TestRegistration:
    """Dynamic registration is a public-client registration."""

    def test_register_sends_the_documented_public_client_fields(self):
        captured: dict = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.update(json.loads(request.content))
            return httpx2.Response(201, json={"client_id": "client-1"})

        registration = oauth.register_client(
            _metadata(), "https://app.example.com/coros/callback", client=_client(handler)
        )

        assert registration.client_id == "client-1"
        assert registration.client_secret is None
        assert captured["redirect_uris"] == ["https://app.example.com/coros/callback"]
        assert captured["grant_types"] == ["authorization_code", "refresh_token"]
        assert captured["token_endpoint_auth_method"] == "none"
        assert captured["scope"] == "openid offline_access mcp.tools"

    def test_registration_without_a_client_id_is_a_protocol_error(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(201, json={})

        with pytest.raises(oauth.CorosProtocolError):
            oauth.register_client(_metadata(), "https://app.example.com/coros/callback", client=_client(handler))

    def test_a_rate_limited_registration_preserves_the_retry_time(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(429, headers={"retry-after": "90"})

        with pytest.raises(core_exceptions.TooManyRequestsError) as caught:
            oauth.register_client(_metadata(), "https://app.example.com/coros/callback", client=_client(handler))

        assert caught.value.retry_at is not None


class TestAuthorizationUrl:
    """The browser URL carries PKCE, state and the resource audience."""

    def test_url_contains_every_required_parameter(self):
        url = oauth.build_authorization_url(
            _metadata(),
            "client-1",
            "https://app.example.com/coros/callback",
            "state-1",
            "challenge-1",
        )

        assert url.startswith("https://mcpeu.coros.com/oauth2/authorize?")
        assert "response_type=code" in url
        assert "client_id=client-1" in url
        assert "code_challenge=challenge-1" in url
        assert "code_challenge_method=S256" in url
        assert "resource=https%3A%2F%2Fmcpeu.coros.com%2Fmcp" in url
        assert "state=state-1" in url


class TestTokens:
    """Token exchange, rotation and error mapping."""

    def test_exchange_code_returns_the_token_set(self):
        captured: dict = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.update({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
            return httpx2.Response(
                200,
                json={
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 7200,
                    "scope": "openid offline_access mcp.tools",
                },
            )

        tokens = oauth.exchange_code(
            _metadata(),
            contracts.CorosClientRegistration("client-1"),
            "code-1",
            "https://app.example.com/coros/callback",
            "verifier-1",
            client=_client(handler),
        )

        assert tokens.access_token == "access"
        assert tokens.refresh_token == "refresh"
        assert captured["grant_type"] == "authorization_code"
        assert captured["code_verifier"] == "verifier-1"
        assert captured["resource"] == "https://mcpeu.coros.com/mcp"

    def test_invalid_grant_requires_reconnection(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(400, json={"error": "invalid_grant"})

        with pytest.raises(oauth.CorosAuthenticationError):
            oauth.exchange_code(
                _metadata(),
                contracts.CorosClientRegistration("client-1"),
                "code-1",
                "https://app.example.com/coros/callback",
                "verifier-1",
                client=_client(handler),
            )

    def test_a_non_string_error_field_is_a_protocol_error(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(400, json={"error": []})

        with pytest.raises(oauth.CorosProtocolError):
            oauth.exchange_code(
                _metadata(),
                contracts.CorosClientRegistration("client-1"),
                "code-1",
                "https://app.example.com/coros/callback",
                "verifier-1",
                client=_client(handler),
            )

    def test_a_rate_limited_token_request_preserves_the_retry_time(self):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(429, headers={"retry-after": "120"})

        with pytest.raises(core_exceptions.TooManyRequestsError) as caught:
            oauth.exchange_code(
                _metadata(),
                contracts.CorosClientRegistration("client-1"),
                "code-1",
                "https://app.example.com/coros/callback",
                "verifier-1",
                client=_client(handler),
            )

        assert caught.value.retry_at is not None

    @pytest.mark.parametrize("expires_in", ["not-a-number", -1, 1e100])
    def test_an_unrepresentable_expiry_is_a_protocol_error(self, expires_in):
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                json={"access_token": "access", "refresh_token": "refresh", "expires_in": expires_in},
            )

        with pytest.raises(oauth.CorosProtocolError):
            oauth.exchange_code(
                _metadata(),
                contracts.CorosClientRegistration("client-1"),
                "code-1",
                "https://app.example.com/coros/callback",
                "verifier-1",
                client=_client(handler),
            )

    def test_refresh_retains_the_old_refresh_token_when_coros_omits_a_new_one(self):
        captured: dict = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.update({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
            return httpx2.Response(200, json={"access_token": "new-access", "expires_in": 60})

        tokens = oauth.refresh_tokens(
            _metadata(),
            contracts.CorosClientRegistration("client-1"),
            "old-refresh",
            client=_client(handler),
        )

        assert tokens.access_token == "new-access"
        assert tokens.refresh_token == "old-refresh"
        assert captured["resource"] == "https://mcpeu.coros.com/mcp"

    def test_revocation_posts_the_token_and_hint(self):
        captured: dict = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.update({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
            return httpx2.Response(200)

        oauth.revoke_token(
            _metadata(),
            contracts.CorosClientRegistration("client-1"),
            "refresh-1",
            "refresh_token",
            client=_client(handler),
        )

        assert captured["token"] == "refresh-1"
        assert captured["token_type_hint"] == "refresh_token"
        assert captured["client_id"] == "client-1"

    def test_revocation_is_skipped_without_an_advertised_endpoint(self):
        requested: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requested.append(request.url.path)
            return httpx2.Response(200)

        oauth.revoke_token(
            replace(_metadata(), revocation_endpoint=None),
            contracts.CorosClientRegistration("client-1"),
            "refresh-1",
            "refresh_token",
            client=_client(handler),
        )

        assert requested == []
