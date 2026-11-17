"""Tests for OIDC ID-token verification.

The signature/claim/nonce paths use **real RSA signing** (joserfc) rather than mocked crypto, so the
tests prove the verifier rejects forged ``alg`` headers (``alg=none`` / RS256->HS256 confusion), unknown
keys, bad signatures, expired tokens, claim mismatches and nonce replay. Only the JWKS fetch is mocked.
"""

import base64
import hashlib
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from joserfc import jwt
from joserfc.jwk import ECKey, OctKey, RSAKey

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


def _sign_without_kid(key: RSAKey, claims: dict) -> str:
    """Sign claims with a header that carries no ``kid``."""
    return jwt.encode({"alg": "RS256"}, claims, key)


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

    def test_eddsa_is_rejected(self, service):
        """joserfc refuses EdDSA by default, so the allow-list does not offer it."""
        token = _fake_jwt({"alg": "EdDSA", "kid": KID})
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

    def test_a_kid_missing_from_the_cached_set_is_looked_up_in_a_fresh_set(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        stale = {"keys": [{**rsa_key.as_dict(private=False), "kid": "older-kid"}]}
        fetch = MagicMock(side_effect=[stale, _public_jwks(rsa_key)])
        with patch.object(service, "fetch_jwks", fetch):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
        assert claims["sub"] == "user-1"
        assert fetch.call_args_list[0].args == (JWKS_URI,)
        assert fetch.call_args_list[0].kwargs == {}
        assert fetch.call_args_list[1].args == (JWKS_URI,)
        assert fetch.call_args_list[1].kwargs == {"refresh": True}

    def test_a_kid_missing_from_the_fresh_set_too_is_an_unknown_key(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        stale = {"keys": [{**rsa_key.as_dict(private=False), "kid": "older-kid"}]}
        fetch = MagicMock(return_value=stale)
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()
        assert fetch.call_count == 2

    def test_a_key_rotated_under_a_cached_kid_is_verified_with_a_fresh_set(self, service, rsa_key, other_rsa_key):
        token = _sign(rsa_key, _valid_claims())
        fetch = MagicMock(side_effect=[_public_jwks(other_rsa_key), _public_jwks(rsa_key)])
        with patch.object(service, "fetch_jwks", fetch):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
        assert claims["sub"] == "user-1"
        assert fetch.call_count == 2
        assert fetch.call_args_list[0].args == (JWKS_URI,)
        assert fetch.call_args_list[0].kwargs == {}
        assert fetch.call_args_list[1].args == (JWKS_URI,)
        assert fetch.call_args_list[1].kwargs == {"refresh": True}

    def test_a_signature_that_fails_with_the_fresh_key_too_is_refused_after_one_refresh(
        self, service, rsa_key, other_rsa_key
    ):
        token = _sign(rsa_key, _valid_claims())
        fetch = MagicMock(return_value=_public_jwks(other_rsa_key))
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in exc_info.value.detail.lower()
        assert fetch.call_count == 2
        assert fetch.call_args_list[1].kwargs == {"refresh": True}

    def test_a_bad_signature_after_the_kid_lookup_refreshed_does_not_refresh_again(
        self, service, rsa_key, other_rsa_key
    ):
        token = _sign(rsa_key, _valid_claims())
        stale = {"keys": [{**rsa_key.as_dict(private=False), "kid": "older-kid"}]}
        fetch = MagicMock(side_effect=[stale, _public_jwks(other_rsa_key)])
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "signature" in exc_info.value.detail.lower()
        assert fetch.call_count == 2

    def test_a_key_gone_from_the_fresh_set_after_a_bad_signature_is_an_unknown_key(
        self, service, rsa_key, other_rsa_key
    ):
        token = _sign(rsa_key, _valid_claims())
        gone = {"keys": [{**rsa_key.as_dict(private=False), "kid": "older-kid"}]}
        fetch = MagicMock(side_effect=[_public_jwks(other_rsa_key), gone])
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()
        assert fetch.call_count == 2

    def test_a_known_kid_does_not_refetch(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        fetch = MagicMock(return_value=_public_jwks(rsa_key))
        with patch.object(service, "fetch_jwks", fetch):
            _verify(service, token, JWKS_URI, ISS, AUD)
        fetch.assert_called_once_with(JWKS_URI)

    def test_a_token_without_kid_is_verified_with_the_only_usable_key(self, service, rsa_key):
        token = _sign_without_kid(rsa_key, _valid_claims())
        jwks = {"keys": [{**rsa_key.as_dict(private=False), "use": "sig"}]}
        fetch = MagicMock(return_value=jwks)
        with patch.object(service, "fetch_jwks", fetch):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
        assert claims["sub"] == "user-1"
        fetch.assert_called_once_with(JWKS_URI)

    def test_keys_of_another_use_type_or_algorithm_are_not_candidates(self, service, rsa_key, other_rsa_key):
        token = _sign_without_kid(rsa_key, _valid_claims())
        ec_key = ECKey.generate_key("P-256")
        jwks = {
            "keys": [
                {**other_rsa_key.as_dict(private=False), "use": "enc"},
                {**other_rsa_key.as_dict(private=False), "alg": "RS512"},
                ec_key.as_dict(private=False),
                rsa_key.as_dict(private=False),
            ]
        }
        with patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
        assert claims["sub"] == "user-1"

    def test_a_token_without_kid_is_refused_when_several_keys_could_have_signed_it(
        self, service, rsa_key, other_rsa_key
    ):
        token = _sign_without_kid(rsa_key, _valid_claims())
        jwks = {"keys": [rsa_key.as_dict(private=False), other_rsa_key.as_dict(private=False)]}
        fetch = MagicMock(return_value=jwks)
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()
        assert fetch.call_count == 2

    def test_a_token_without_kid_is_refused_when_no_key_could_have_signed_it(self, service, rsa_key):
        token = _sign_without_kid(rsa_key, _valid_claims())
        fetch = MagicMock(return_value={"keys": []})
        with (
            patch.object(service, "fetch_jwks", fetch),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert fetch.call_count == 2

    def test_a_token_without_kid_looks_in_a_fresh_set_when_the_cached_one_has_no_candidate(self, service, rsa_key):
        token = _sign_without_kid(rsa_key, _valid_claims())
        fetch = MagicMock(side_effect=[{"keys": []}, {"keys": [rsa_key.as_dict(private=False)]}])
        with patch.object(service, "fetch_jwks", fetch):
            claims = _verify(service, token, JWKS_URI, ISS, AUD)
        assert claims["sub"] == "user-1"
        assert fetch.call_args_list[1].kwargs == {"refresh": True}

    def test_a_token_naming_a_kid_still_needs_that_key_even_when_the_set_has_one_key(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims(), kid="named")
        jwks = {"keys": [rsa_key.as_dict(private=False)]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert "unknown key" in exc_info.value.detail.lower()

    def test_a_key_of_an_unsupported_type_is_an_unknown_key(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{"kid": KID, "kty": "UNKNOWN"}]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()

    @pytest.mark.parametrize(
        "advertised",
        [
            pytest.param(lambda: ECKey.generate_key("P-256"), id="ec"),
            pytest.param(lambda: OctKey.generate_key(256), id="oct"),
        ],
    )
    def test_a_key_that_cannot_verify_the_algorithm_raises_401(self, service, rsa_key, advertised):
        """An RS256 token whose kid names a key of another type is refused as unverifiable, not a server error."""
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**advertised().as_dict(private=False), "kid": KID}]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


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

    def test_missing_subject_raises_401(self, service, rsa_key):
        claims = _valid_claims()
        del claims["sub"]
        token = _sign(rsa_key, claims)
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "sub" in exc_info.value.detail


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


# ---------------------------------------------------------------------------
# Key selection by kid honours ``use`` and ``alg``
# ---------------------------------------------------------------------------


class TestVerifyIdTokenKeyAttributes:
    """A key found by ``kid`` must also be a signature key for the token's algorithm."""

    @pytest.mark.parametrize("attributes", [{"use": "enc"}, {"alg": "RS512"}])
    def test_a_key_named_by_kid_that_cannot_verify_this_token_is_an_unknown_key(self, service, rsa_key, attributes):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**_public_jwks(rsa_key)["keys"][0], **attributes}]}
        with (
            patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            _verify(service, token, JWKS_URI, ISS, AUD)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "unknown key" in exc_info.value.detail.lower()

    def test_a_key_that_declares_signature_use_and_the_token_algorithm_verifies(self, service, rsa_key):
        token = _sign(rsa_key, _valid_claims())
        jwks = {"keys": [{**_public_jwks(rsa_key)["keys"][0], "use": "sig", "alg": "RS256"}]}
        with patch.object(service, "fetch_jwks", MagicMock(return_value=jwks)):
            assert _verify(service, token, JWKS_URI, ISS, AUD)["sub"] == "user-1"


# ---------------------------------------------------------------------------
# at_hash (OIDC Core 3.1.3.6)
# ---------------------------------------------------------------------------


def _at_hash(access_token: str, digest) -> str:
    half = digest(access_token.encode()).digest()
    return base64.urlsafe_b64encode(half[: len(half) // 2]).decode().rstrip("=")


class TestVerifyIdTokenAccessTokenHash:
    """An ID token's ``at_hash`` must match the access token issued with it."""

    def _verify_with(self, service, rsa_key, claims, access_token):
        token = _sign(rsa_key, claims)
        with patch.object(service, "fetch_jwks", MagicMock(return_value=_public_jwks(rsa_key))):
            return _verify(service, token, JWKS_URI, ISS, AUD, access_token=access_token)

    def test_a_matching_at_hash_verifies(self, service, rsa_key):
        claims = _valid_claims(at_hash=_at_hash("access-token", hashlib.sha256))
        assert self._verify_with(service, rsa_key, claims, "access-token")["sub"] == "user-1"

    @pytest.mark.parametrize(
        ("alg", "digest"),
        [("PS256", hashlib.sha256), ("ES384", hashlib.sha384), ("RS512", hashlib.sha512)],
    )
    def test_the_hash_is_the_one_of_the_signature_algorithm(self, alg, digest):
        id_token_service._require_access_token_hash(_at_hash("access-token", digest), "access-token", alg)
        with pytest.raises(core_exceptions.UnauthenticatedError):
            id_token_service._require_access_token_hash(_at_hash("access-token", hashlib.sha1), "access-token", alg)

    def test_a_mismatching_at_hash_is_refused(self, service, rsa_key):
        claims = _valid_claims(at_hash=_at_hash("another-token", hashlib.sha256))
        with pytest.raises(core_exceptions.UnauthenticatedError, match="at_hash"):
            self._verify_with(service, rsa_key, claims, "access-token")

    def test_an_at_hash_that_is_not_a_string_is_refused(self, service, rsa_key):
        with pytest.raises(core_exceptions.UnauthenticatedError, match="at_hash"):
            self._verify_with(service, rsa_key, _valid_claims(at_hash=7), "access-token")

    def test_an_at_hash_is_not_checked_without_an_access_token(self, service, rsa_key):
        claims = _valid_claims(at_hash="anything")
        assert self._verify_with(service, rsa_key, claims, None)["sub"] == "user-1"

    def test_a_token_without_at_hash_verifies_with_an_access_token(self, service, rsa_key):
        assert self._verify_with(service, rsa_key, _valid_claims(), "access-token")["sub"] == "user-1"
