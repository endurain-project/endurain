"""ID-token checks of the authorized party and the clock skew (OIDC Core 3.1.3.7)."""

import time

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

import core.exceptions as core_exceptions
import modules.auth.identity_providers.id_token_service as id_token_service

KID = "azp-test-key"
ISSUER = "https://idp.example.com"
CLIENT_ID = "endurain"


@pytest.fixture(scope="module")
def key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": KID})


def _verify(key: RSAKey, **overrides) -> dict:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "subject-1", "iat": now, "exp": now + 300} | overrides
    claims = {name: value for name, value in claims.items() if value is not None}
    token = jwt.encode({"alg": "RS256", "kid": KID}, claims, key)
    jwks = {"keys": [key.as_dict(private=False)]}
    return id_token_service.verify_id_token(lambda _uri: jwks, token, "https://idp.example.com/jwks", ISSUER, CLIENT_ID)


class TestAuthorizedParty:
    def test_a_token_issued_to_this_client_passes(self, key):
        assert _verify(key, azp=CLIENT_ID)["sub"] == "subject-1"

    def test_a_single_audience_needs_no_authorized_party(self, key):
        assert _verify(key)["sub"] == "subject-1"

    def test_several_audiences_with_this_client_as_authorized_party_pass(self, key):
        assert _verify(key, aud=[CLIENT_ID, "other"], azp=CLIENT_ID)["sub"] == "subject-1"

    def test_a_token_issued_to_another_client_is_refused(self, key):
        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(key, aud=[CLIENT_ID, "other"], azp="other")

    def test_several_audiences_without_an_authorized_party_are_refused(self, key):
        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(key, aud=[CLIENT_ID, "other"])


class TestClockSkew:
    def test_a_token_expired_within_the_leeway_passes(self, key):
        now = int(time.time())

        assert _verify(key, iat=now - 300, exp=now - 30)["sub"] == "subject-1"

    def test_a_token_expired_beyond_the_leeway_is_refused(self, key):
        now = int(time.time())

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(key, iat=now - 600, exp=now - id_token_service.ID_TOKEN_CLOCK_LEEWAY_SECONDS - 30)
