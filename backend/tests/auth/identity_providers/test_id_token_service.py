"""Tests for OIDC ID-token verification.

The signature/claim/nonce paths use **real RSA signing** (joserfc) rather than mocked crypto, so the
tests prove the verifier rejects forged ``alg`` headers (``alg=none`` / RS256->HS256 confusion), unknown
keys, bad signatures, expired tokens, claim mismatches and nonce replay. Only the JWKS fetch is mocked.
"""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from joserfc import jwt
from joserfc.jwk import RSAKey

import core.exceptions as core_exceptions
import modules.auth.identity_providers.id_token_service as id_token_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

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
def service() -> oidc_client_service.OidcClientService:
    """Return a client whose ``fetch_jwks`` is what the verifier asks for signing keys."""
    return oidc_client_service.OidcClientService(MagicMock(), "test")


def _verify(service, token, jwks_uri, issuer, audience, **kwargs):
    return id_token_service.verify_id_token(service.fetch_jwks, token, jwks_uri, issuer, audience, **kwargs)


# ---------------------------------------------------------------------------
# verify_id_token — header / algorithm guards (pre-signature)
# ---------------------------------------------------------------------------


class TestVerifyIdTokenHeaderGuards:
    """Header-shape and algorithm allow-list checks reject before fetch."""

    def test_malformed_token_not_three_parts_raises_401(self, service):
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            _verify(service, "only.two", JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "format" in exc_info.value.detail.lower()

    def test_missing_kid_raises_401(self, service):
        token = _fake_jwt({"alg": "RS256"})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key identifier" in exc_info.value.detail.lower()

    def test_missing_alg_raises_401(self, service):
        token = _fake_jwt({"kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "algorithm" in exc_info.value.detail.lower()

    def test_alg_none_is_rejected(self, service):
        """alg=none must be rejected (signature-bypass attack)."""
        token = _fake_jwt({"alg": "none", "kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()

    def test_symmetric_hs256_is_rejected(self, service):
        """HS256 must be rejected (RS256→HS256 key-confusion attack)."""
        token = _fake_jwt({"alg": "HS256", "kid": KID})
        with pytest.raises(core_exceptions.DomainError) as exc_info:
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unsupported signature algorithm" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# verify_id_token — JWKS key resolution
# ---------------------------------------------------------------------------


class TestVerifyIdTokenKeyResolution:
    """Key lookup in the JWKS document."""

    def test_no_matching_kid_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**rsa_key.as_dict(private=False), "kid": "different-kid"}]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()

    def test_unsupported_key_type_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{"kid": KID, "kty": "UNKNOWN"}]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key type" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# verify_id_token — real signature & claim verification
# ---------------------------------------------------------------------------


class TestVerifyIdTokenSignatureAndClaims:
    """End-to-end verification with real RSA signing."""

    def test_valid_token_returns_claims(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"
            assert claims["iss"] == ISS

    def test_signature_from_wrong_key_raises_401(self, service, rsa_key, other_rsa_key):
        """Token signed by a different private key (same kid) must fail."""
        token = _sign(rsa_key, _valid_claims())
        # JWKS advertises the *other* key's public half under the same kid.
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(other_rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in exc_info.value.detail.lower()

    def test_expired_token_raises_401(self, service, rsa_key):
        now = int(time.time())
        token = _sign(rsa_key, _valid_claims(exp=now - 120, iat=now - 3600))
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    def test_issuer_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(iss="https://evil.example.com"))
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "claim" in exc_info.value.detail.lower()

    def test_audience_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(aud="some-other-client"))
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# verify_id_token — nonce replay protection
# ---------------------------------------------------------------------------


class TestVerifyIdTokenNonce:
    """Nonce binding prevents ID-token replay across sessions."""

    def test_matching_nonce_passes(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="session-nonce"))
        with patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = _verify(service, token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
            assert claims["nonce"] == "session-nonce"

    def test_missing_nonce_when_expected_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())  # no nonce claim
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce" in exc_info.value.detail.lower()

    def test_nonce_mismatch_raises_401(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(nonce="attacker-nonce"))
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD, expected_nonce="session-nonce")
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "nonce mismatch" in exc_info.value.detail.lower()

    def test_nonce_not_checked_when_not_expected(self, service, rsa_key):
        """When no nonce is expected, a token without nonce still verifies."""
        token = _sign(rsa_key, _valid_claims())
        with patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
            assert claims["sub"] == "user-1"
