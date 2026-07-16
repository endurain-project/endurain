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
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException, status
from joserfc import jwt
from joserfc.jwk import RSAKey

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


@pytest.fixture
def service() -> IdentityProviderService:
    """Return a fresh service instance with empty caches."""
    return IdentityProviderService()


# ---------------------------------------------------------------------------
# _verify_id_token — header / algorithm guards (pre-signature)
# ---------------------------------------------------------------------------


class TestVerifyIdTokenHeaderGuards:
    """Header-shape and algorithm allow-list checks reject before fetch."""

    @pytest.mark.asyncio
    async def test_malformed_token_not_three_parts_raises_401(self, service):
        with pytest.raises(HTTPException) as exc_info:
            await service._verify_id_token("only.two", JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "format" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_missing_kid_raises_401(self, service):
        token = _fake_jwt({"alg": "RS256"})
        with pytest.raises(HTTPException) as exc_info:
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key identifier" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_missing_alg_raises_401(self, service):
        token = _fake_jwt({"kid": KID})
        with pytest.raises(HTTPException) as exc_info:
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "algorithm" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_alg_none_is_rejected(self, service):
        """alg=none must be rejected (signature-bypass attack)."""
        token = _fake_jwt({"alg": "none", "kid": KID})
        with pytest.raises(HTTPException) as exc_info:
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_symmetric_hs256_is_rejected(self, service):
        """HS256 must be rejected (RS256→HS256 key-confusion attack)."""
        token = _fake_jwt({"alg": "HS256", "kid": KID})
        with pytest.raises(HTTPException) as exc_info:
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# _verify_id_token — JWKS key resolution
# ---------------------------------------------------------------------------


class TestVerifyIdTokenKeyResolution:
    """Key lookup in the JWKS document."""

    @pytest.mark.asyncio
    async def test_no_matching_kid_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**rsa_key.as_dict(private=False), "kid": "different-kid"}]}
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=jwks)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_unsupported_key_type_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{"kid": KID, "kty": "UNKNOWN"}]}
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=jwks)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key type" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# _verify_id_token — real signature & claim verification
# ---------------------------------------------------------------------------


class TestVerifyIdTokenSignatureAndClaims:
    """End-to-end verification with real RSA signing."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_claims(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))):
            claims = await service._verify_id_token(token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"
            assert claims["iss"] == ISS

    @pytest.mark.asyncio
    async def test_signature_from_wrong_key_raises_401(self, service, rsa_key, other_rsa_key):
        """Token signed by a different private key (same kid) must fail."""
        token = _sign(rsa_key, _valid_claims())
        # JWKS advertises the *other* key's public half under the same kid.
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(other_rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, service, rsa_key):
        now = int(time.time())
        token = _sign(rsa_key, _valid_claims(exp=now - 10, iat=now - 3600))
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_issuer_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(iss="https://evil.example.com"))
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "claim" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_audience_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(aud="some-other-client"))
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# _verify_id_token — nonce replay protection
# ---------------------------------------------------------------------------


class TestVerifyIdTokenNonce:
    """Nonce binding prevents ID-token replay across sessions."""

    @pytest.mark.asyncio
    async def test_matching_nonce_passes(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="session-nonce"))
        with patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))):
            claims = await service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
            assert claims["nonce"] == "session-nonce"

    @pytest.mark.asyncio
    async def test_missing_nonce_when_expected_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())  # no nonce claim
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_nonce_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="attacker-nonce"))
        with (
            patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._verify_id_token(token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce mismatch" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_nonce_not_checked_when_not_expected(self, service, rsa_key):
        """When no nonce is expected, a token without nonce still verifies."""
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "_fetch_jwks", AsyncMock(return_value=_public_jwks(rsa_key))):
            claims = await service._verify_id_token(token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"


# ---------------------------------------------------------------------------
# _fetch_jwks
# ---------------------------------------------------------------------------


class TestFetchJwks:
    """JWKS retrieval: caching, SSRF guard, and error mapping."""

    def _client_returning(self, *, json_value=None, raise_for_status_exc=None, get_exc=None) -> AsyncMock:
        """Build a mock httpx.AsyncClient with a single GET behaviour."""
        client = AsyncMock()
        if get_exc is not None:
            client.get = AsyncMock(side_effect=get_exc)
            return client
        response = MagicMock()
        if raise_for_status_exc is not None:
            response.raise_for_status.side_effect = raise_for_status_exc
        else:
            response.raise_for_status.return_value = None
        response.json.return_value = json_value
        client.get = AsyncMock(return_value=response)
        return client

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_network(self, service):
        from datetime import UTC, datetime

        cached = {"keys": [{"kid": KID, "kty": "RSA"}]}
        service._jwks_cache[JWKS_URI] = {"jwks": cached, "cached_at": datetime.now(UTC)}
        with patch.object(service, "_get_http_client", AsyncMock()) as mock_client:
            result = await service._fetch_jwks(JWKS_URI)
        assert result is cached
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_fetch_caches_result(self, service):
        jwks = {"keys": [{"kid": KID, "kty": "RSA"}]}
        client = self._client_returning(json_value=jwks)
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_get_http_client", AsyncMock(return_value=client)),
        ):
            result = await service._fetch_jwks(JWKS_URI)
            assert result == jwks
            assert JWKS_URI in service._jwks_cache

    @pytest.mark.asyncio
    async def test_invalid_structure_is_rejected(self, service):
        # NOTE: the source raises 502 for a malformed JWKS, but _fetch_jwks has
        # no ``except HTTPException: raise`` clause, so that 502 is caught by
        # the trailing ``except Exception`` and downgraded to a generic 500.
        # This test pins the *actual* behaviour rather than the intended 502.
        client = self._client_returning(json_value={"no_keys": True})
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_get_http_client", AsyncMock(return_value=client)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_timeout_raises_504(self, service):
        client = self._client_returning(get_exc=httpx.TimeoutException("timeout"))
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_get_http_client", AsyncMock(return_value=client)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @pytest.mark.asyncio
    async def test_http_status_error_raises_502(self, service):
        err = httpx.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        client = self._client_returning(raise_for_status_exc=err)
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_get_http_client", AsyncMock(return_value=client)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service._fetch_jwks(JWKS_URI)
            assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    @pytest.mark.asyncio
    async def test_ssrf_guard_blocks_before_any_fetch(self, service):
        """A private/internal JWKS URL must be blocked before any HTTP call.

        The SSRF guard fires before ``_get_http_client``/``client.get``, so no
        outbound request is ever made. NOTE: because the guard runs *inside*
        the try block and ``_fetch_jwks`` lacks an ``except HTTPException:
        raise`` clause, the guard's 4xx is downgraded to a generic 500 by the
        trailing ``except Exception``. The request is still blocked; only the
        surfaced status code is coarser than the guard intended.
        """
        with (
            patch(
                "modules.auth.identity_providers.service.core_network.reject_private_url",
                side_effect=HTTPException(status_code=400, detail="blocked"),
            ),
            patch.object(service, "_get_http_client", AsyncMock()) as mock_client,
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._fetch_jwks("http://169.254.169.254/jwks")
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# _get_userinfo
# ---------------------------------------------------------------------------


class TestGetUserinfo:
    """Orchestration of userinfo endpoint and verified ID-token claims."""

    @pytest.mark.asyncio
    async def test_userinfo_endpoint_only_returns_claims(self, service):
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sub": "user-1", "email": "a@example.com"}
        client.get = AsyncMock(return_value=response)
        with patch("modules.auth.identity_providers.service.core_network.reject_private_url"):
            result = await service._get_userinfo(
                token_response={"access_token": "at"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=None,
                expected_issuer=None,
                expected_audience=AUD,
            )
        assert result == {"sub": "user-1", "email": "a@example.com"}

    @pytest.mark.asyncio
    async def test_id_token_claims_override_userinfo_on_merge(self, service):
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sub": "endpoint-sub", "name": "From Endpoint"}
        client.get = AsyncMock(return_value=response)
        verified = {"sub": "verified-sub", "email": "v@example.com"}
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_verify_id_token", AsyncMock(return_value=verified)),
        ):
            result = await service._get_userinfo(
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

    @pytest.mark.asyncio
    async def test_id_token_only_returns_verified_claims(self, service):
        verified = {"sub": "verified-sub"}
        with patch.object(service, "_verify_id_token", AsyncMock(return_value=verified)):
            result = await service._get_userinfo(
                token_response={"id_token": "idt"},
                userinfo_endpoint=None,
                client=AsyncMock(),
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert result == verified

    @pytest.mark.asyncio
    async def test_id_token_verification_failure_is_reraised(self, service):
        with (
            patch.object(
                service,
                "_verify_id_token",
                AsyncMock(side_effect=HTTPException(status_code=401, detail="bad signature")),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._get_userinfo(
                token_response={"id_token": "idt"},
                userinfo_endpoint=None,
                client=AsyncMock(),
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_userinfo_and_no_verifiable_id_token_raises_500(self, service):
        """Nothing to return → fail closed with 500."""
        result_client = AsyncMock()
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._get_userinfo(
                token_response={},
                userinfo_endpoint=None,
                client=result_client,
                jwks_uri=None,
                expected_issuer=None,
                expected_audience=AUD,
            )
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_endpoint_failure_falls_back_to_verified_id_token(self, service):
        """If the userinfo endpoint errors, a verified ID token still wins."""
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.RequestError("network down"))
        verified = {"sub": "verified-sub"}
        with (
            patch("modules.auth.identity_providers.service.core_network.reject_private_url"),
            patch.object(service, "_verify_id_token", AsyncMock(return_value=verified)),
        ):
            result = await service._get_userinfo(
                token_response={"access_token": "at", "id_token": "idt"},
                userinfo_endpoint="https://idp.example.com/userinfo",
                client=client,
                jwks_uri=JWKS_URI,
                expected_issuer=ISS,
                expected_audience=AUD,
            )
        assert result == verified
