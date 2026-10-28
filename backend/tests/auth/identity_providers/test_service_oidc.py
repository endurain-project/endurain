"""Tests for the security-critical OIDC network-flow methods of
IdentityProviderService.

Covers the previously-untested methods flagged as the largest remaining auth
gap:

- ``_verify_id_token`` — OIDC ID-token signature + claim verification. The
  signature/claim/nonce paths use **real RSA signing** (joserfc) rather than
  mocked crypto, so the tests actually prove the verifier rejects forged
  ``alg`` headers (``alg=none`` / RS256→HS256 confusion), unknown keys, bad
  signatures, expired tokens, claim mismatches, and nonce replay.
- ``_fetch_jwks`` — JWKS retrieval with caching, SSRF guard, and the
  network/format error → HTTP-status mapping.
- ``_get_userinfo`` — orchestration: userinfo-endpoint vs ID-token precedence,
  merge semantics, and fail-closed behaviour.

Only the HTTP transport and the SSRF guard are mocked; the cryptographic
verification is exercised end to end.
"""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import httpx2
import pytest
from fastapi import status
from joserfc import jwt
from joserfc.jwk import RSAKey

import core.exceptions as core_exceptions
from modules.auth.identity_providers.service import IdentityProviderService

# ---------------------------------------------------------------------------
# Test constants and real-key fixtures
# ---------------------------------------------------------------------------

KID = "test-key-1"
ISS = "https://idp.example.com"
AUD = "client-id-123"
JWKS_URI = "https://idp.example.com/jwks"


@pytest.fixture(scope="module")
def rsa_key() -> RSAKey:
    """Generate a single RSA key pair reused across the module.

    Returns:
        RSAKey: A 2048-bit RSA key with a fixed ``kid``.
    """
    return RSAKey.generate_key(2048, parameters={"kid": KID})


@pytest.fixture(scope="module")
def other_rsa_key() -> RSAKey:
    """A second RSA key sharing the same ``kid`` for signature-mismatch tests.

    Returns:
        RSAKey: A different 2048-bit RSA key advertised under the same ``kid``.
    """
    return RSAKey.generate_key(2048, parameters={"kid": KID})


def _public_jwks(key: RSAKey) -> dict:
    """Build a JWKS document containing the public half of ``key``."""
    return {"keys": [{**key.as_dict(private=False), "kid": KID}]}


def _sign(key: RSAKey, claims: dict, *, alg: str = "RS256", kid: str = KID) -> str:
    """Sign ``claims`` into a JWT using ``key``."""
    return jwt.encode({"alg": alg, "kid": kid}, claims, key)


def _valid_claims(**overrides) -> dict:
    """Return a baseline set of valid OIDC claims, with optional overrides."""
    now = int(time.time())
    claims = {
        "iss": ISS,
        "aud": AUD,
        "sub": "user-1",
        "exp": now + 3600,
        "iat": now,
    }
    claims.update(overrides)
    return claims


def _fake_jwt(header: dict, payload: dict | None = None) -> str:
    """Craft an unsigned JWT-shaped string with the given header.

    Used for header-parsing/algorithm checks that run *before* any signature
    verification, so a real signature is unnecessary.
    """

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64(header)}.{b64(payload or {})}.signature"


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


class _NetworkGuardError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


@pytest.fixture
def state_provider() -> _MemoryState:
    return _MemoryState()


@pytest.fixture
def service(state_provider) -> IdentityProviderService:
    """Return a fresh service instance backed by shared test state."""
    return IdentityProviderService(state_provider, "https://app.example", "test")


# ---------------------------------------------------------------------------
# _verify_id_token — header / algorithm guards (pre-signature)
# ---------------------------------------------------------------------------


class TestVerifyIdTokenHeaderGuards:
    """Header-shape and algorithm allow-list checks reject before fetch."""

    def test_malformed_token_not_three_parts_raises_401(self, service):
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            service._verify_id_token("only.two", JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "format" in exc_info.value.detail.lower()

    def test_missing_kid_raises_401(self, service):
        token = _fake_jwt({"alg": "RS256"})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key identifier" in exc_info.value.detail.lower()

    def test_missing_alg_raises_401(self, service):
        token = _fake_jwt({"kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "algorithm" in exc_info.value.detail.lower()

    def test_alg_none_is_rejected(self, service):
        """alg=none must be rejected (signature-bypass attack)."""
        token = _fake_jwt({"alg": "none", "kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()

    def test_symmetric_hs256_is_rejected(self, service):
        """HS256 must be rejected (RS256→HS256 key-confusion attack)."""
        token = _fake_jwt({"alg": "HS256", "kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# _verify_id_token — JWKS key resolution
# ---------------------------------------------------------------------------


class TestVerifyIdTokenKeyResolution:
    """Key lookup in the JWKS document."""

    def test_no_matching_kid_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**rsa_key.as_dict(private=False), "kid": "different-kid"}]}
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()

    def test_unsupported_key_type_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{"kid": KID, "kty": "UNKNOWN"}]}
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key type" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# _verify_id_token — real signature & claim verification
# ---------------------------------------------------------------------------


class TestVerifyIdTokenSignatureAndClaims:
    """End-to-end verification with real RSA signing."""

    def test_valid_token_returns_claims(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = service._verify_id_token(token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"
            assert claims["iss"] == ISS

    def test_signature_from_wrong_key_raises_401(self, service, rsa_key, other_rsa_key):
        """Token signed by a different private key (same kid) must fail."""
        token = _sign(rsa_key, _valid_claims())
        # JWKS advertises the *other* key's public half under the same kid.
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(other_rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in exc_info.value.detail.lower()

    def test_expired_token_raises_401(self, service, rsa_key):
        now = int(time.time())
        token = _sign(rsa_key, _valid_claims(exp=now - 10, iat=now - 3600))
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    def test_issuer_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(iss="https://evil.example.com"))
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "claim" in exc_info.value.detail.lower()

    def test_audience_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(aud="some-other-client"))
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# _verify_id_token — nonce replay protection
# ---------------------------------------------------------------------------


class TestVerifyIdTokenNonce:
    """Nonce binding prevents ID-token replay across sessions."""

    def test_matching_nonce_passes(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="session-nonce"))
        with patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
            assert claims["nonce"] == "session-nonce"

    def test_missing_nonce_when_expected_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())  # no nonce claim
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce" in exc_info.value.detail.lower()

    def test_nonce_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="attacker-nonce"))
        with (
            patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce mismatch" in exc_info.value.detail.lower()

    def test_nonce_not_checked_when_not_expected(self, service, rsa_key):
        """When no nonce is expected, a token without nonce still verifies."""
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "_fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = service._verify_id_token(token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"


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
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_http_client") as mock_client,
        ):
            result = service._fetch_jwks(JWKS_URI)
        assert result == cached
        mock_client.assert_not_called()

    def test_successful_fetch_caches_result(self, service):
        jwks = {"keys": [{"kid": KID, "kty": "RSA"}]}
        client = self._client_returning(json_value=jwks)
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_http_client", MagicMock(return_value=client)),
        ):
            result = service._fetch_jwks(JWKS_URI)
            assert result == jwks
            assert service._jwks_key(JWKS_URI) in service._state.values

    def test_invalid_structure_is_rejected(self, service):
        client = self._client_returning(json_value={"no_keys": True})
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    def test_timeout_raises_504(self, service):
        client = self._client_returning(get_exc=httpx2.TimeoutException("timeout"))
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    def test_http_status_error_raises_502(self, service):
        err = httpx2.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        client = self._client_returning(raise_for_status_exc=err)
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_http_client", MagicMock(return_value=client)),
        ):
            with pytest.raises(core_exceptions.DomainError) as exc_info:
                service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    def test_ssrf_guard_blocks_before_any_fetch(self, service):
        """A private/internal JWKS URL must be blocked before any HTTP call.

        The SSRF guard fires before ``_get_http_client``/``client.get``, and its
        status is preserved for the caller.
        """
        with (
            patch(
                "modules.auth.identity_providers.service.core_network.reject_private_url",
                side_effect=core_exceptions.InvalidInputError("blocked"),
            ),
            patch.object(service, "_http_client", MagicMock()) as mock_client,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._fetch_jwks("http://169.254.169.254/jwks")
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_client.assert_not_called()


class TestGetOidcConfigurationGuardFailures:
    """Discovery logs why the SSRF guard did not clear the issuer URL."""

    @staticmethod
    def _discover_with_guard_failure(service, status_code: int, detail: str):
        idp = MagicMock(issuer_url="https://idp.example.com", id=1)
        idp.name = "Test IdP"
        with (
            patch(
                "modules.auth.identity_providers.service.core_network.reject_private_url",
                side_effect=_NetworkGuardError(status_code, detail),
            ),
            patch("modules.auth.identity_providers.service.logger") as mock_logger,
        ):
            result = service.get_oidc_configuration(idp)
        return result, str(mock_logger.warning.call_args)

    def test_blocked_url_points_the_operator_at_ssrf_allowed_hosts(self, service):
        result, message = self._discover_with_guard_failure(
            service, status.HTTP_400_BAD_REQUEST, "URL resolves to a non-public address"
        )
        assert result is None
        assert "was rejected" in message
        assert "SSRF_ALLOWED_HOSTS" in message

    @pytest.mark.parametrize(
        ("status_code", "detail"),
        [
            (status.HTTP_503_SERVICE_UNAVAILABLE, "Hostname resolution is busy"),
            (status.HTTP_504_GATEWAY_TIMEOUT, "Hostname resolution timed out"),
        ],
    )
    def test_unchecked_url_is_not_blamed_on_the_allowlist(self, service, status_code, detail):
        result, message = self._discover_with_guard_failure(service, status_code, detail)
        assert result is None
        assert "could not be checked" in message
        assert detail in message
        assert "SSRF_ALLOWED_HOSTS" not in message


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

    first = IdentityProviderService(state_provider, "https://app.example", "test")
    second = IdentityProviderService(state_provider, "https://app.example", "test")
    first_client = client_with_document()
    with (
        patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
        patch.object(first, "_http_client", return_value=first_client),
    ):
        assert first.get_oidc_configuration(idp) == document
    first_client.get.assert_called_once()

    with patch.object(second, "_http_client") as second_client:
        assert second.get_oidc_configuration(idp) == document
    second_client.assert_not_called()

    key = first._discovery_key(idp.id)
    state_provider.expiry[key] = time.monotonic() - 1
    expired_client = client_with_document()
    with (
        patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
        patch.object(second, "_http_client", return_value=expired_client),
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
        with patch("modules.auth.identity_providers.service.core_network.reject_private_url"):
            result = service._get_userinfo(
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
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_verify_id_token", MagicMock(return_value=verified)),
        ):
            result = service._get_userinfo(
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
        with patch.object(service, "_verify_id_token", MagicMock(return_value=verified)):
            result = service._get_userinfo(
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
                service,
                "_verify_id_token",
                MagicMock(side_effect=core_exceptions.UnauthenticatedError("bad signature")),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._get_userinfo(
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
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._get_userinfo(
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
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_verify_id_token", MagicMock(return_value=verified)),
        ):
            result = service._get_userinfo(
                token_response={"access_token": "at", "id_token": "idt"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert result == verified


# ---------------------------------------------------------------------------
# handle_callback
# ---------------------------------------------------------------------------


class TestHandleCallback:
    """The callback fetches userinfo after a successful token exchange."""

    def test_login_mode_returns_userinfo_from_token_exchange(self, service):
        idp = MagicMock(issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp")
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, nonce="nonce", redirect_path="/", client_type="web")
        token_response = {"access_token": "at"}
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = token_response
        user = MagicMock(id=1)
        userinfo = {"sub": "user-1", "email": "a@example.com"}

        with (
            patch.object(service, "_decrypt_client_id", return_value=AUD),
            patch.object(service, "_decrypt_client_secret", return_value="secret"),
            patch.object(service, "_resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service, "_create_oauth_client", return_value=oauth_client),
            patch.object(service, "_get_userinfo", return_value=userinfo) as get_userinfo,
            patch.object(service, "_find_or_create_user", return_value=user),
            patch.object(service, "_store_idp_tokens"),
        ):
            result = service.handle_callback(idp, "code", "state", MagicMock(), oauth_state, MagicMock())

        get_userinfo.assert_called_once()
        assert result["userinfo"] == userinfo
        assert result["user"] is user

    def test_the_database_is_not_touched_until_the_identity_provider_has_answered(self, service):
        """The session holds a pooled connection once it is used, so no network call may run after that."""
        idp = MagicMock(issuer_url=None, userinfo_endpoint="https://idp.example.com/userinfo", slug="idp")
        idp.name = "Pocket ID"
        oauth_state = MagicMock(user_id=None, nonce="nonce", redirect_path="/", client_type="web")
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        db = MagicMock()
        order = MagicMock()
        order.attach_mock(oauth_client.fetch_token, "token_exchange")
        order.attach_mock(db, "db")

        with (
            patch.object(service, "_decrypt_client_id", return_value=AUD),
            patch.object(service, "_decrypt_client_secret", return_value="secret"),
            patch.object(service, "_resolve_token_endpoint", return_value="https://idp.example.com/token"),
            patch.object(service, "_create_oauth_client", return_value=oauth_client),
            patch.object(service, "_get_userinfo", return_value={"sub": "user-1"}) as get_userinfo,
            patch.object(service, "_find_or_create_user", return_value=MagicMock(id=1)),
            patch.object(service, "_store_idp_tokens"),
        ):
            order.attach_mock(get_userinfo, "userinfo")
            service.handle_callback(idp, "code", "state", MagicMock(), oauth_state, db)

        names = [call[0] for call in order.mock_calls]
        last_network_call = max(names.index("token_exchange"), names.index("userinfo"))
        assert not any(name.startswith("db") for name in names[: last_network_call + 1])
