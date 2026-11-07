"""Tests for the verification of OIDC back-channel logout tokens (Back-Channel Logout 1.0, section 2.6).

Tokens are signed with real RSA and EC keys; only the JWKS fetch is a stand-in.
"""

import base64
import json
import time

import pytest
from joserfc import jws, jwt
from joserfc.jwk import ECKey, RSAKey

import core.exceptions as core_exceptions
import modules.auth.identity_providers.id_token_service as id_token_service

KID = "logout-key"
ISS = "https://idp.example.com"
AUD = "endurain-client"
JWKS_URI = "https://idp.example.com/jwks"
EVENT = "http://schemas.openid.net/event/backchannel-logout"


@pytest.fixture(scope="module")
def rsa_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": KID})


@pytest.fixture(scope="module")
def ec_key() -> ECKey:
    return ECKey.generate_key("P-256", parameters={"kid": "ec-key"})


def _jwks(*keys) -> dict:
    return {"keys": [key.as_dict(private=False) for key in keys]}


def _claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "iss": ISS,
        "aud": AUD,
        "iat": now,
        "exp": now + 120,
        "jti": "jti-1",
        "sid": "provider-session",
        "sub": "subject-1",
        "events": {EVENT: {}},
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _sign(key, claims: dict, **header) -> str:
    return jwt.encode({"alg": "RS256", "kid": KID, "typ": "logout+jwt", **header}, claims, key)


def _verify(token: str, jwks: dict) -> dict:
    return id_token_service.verify_logout_token(lambda _uri, refresh=False: jwks, token, JWKS_URI, ISS, AUD)


def _refused(token: str, jwks: dict) -> core_exceptions.UnauthenticatedError:
    with pytest.raises(core_exceptions.UnauthenticatedError) as exc_info:
        _verify(token, jwks)
    return exc_info.value


class TestAcceptedLogoutTokens:
    def test_a_valid_token_returns_its_claims(self, rsa_key):
        claims = _verify(_sign(rsa_key, _claims()), _jwks(rsa_key))

        assert (claims["sid"], claims["sub"], claims["jti"]) == ("provider-session", "subject-1", "jti-1")

    def test_an_ec_signed_token_verifies(self, ec_key):
        token = jwt.encode({"alg": "ES256", "kid": "ec-key", "typ": "logout+jwt"}, _claims(), ec_key)

        assert _verify(token, _jwks(ec_key))["sid"] == "provider-session"

    def test_a_token_without_typ_is_accepted(self, rsa_key):
        token = jws.serialize_compact({"alg": "RS256", "kid": KID}, json.dumps(_claims()), rsa_key)

        assert _verify(token, _jwks(rsa_key))["jti"] == "jti-1"

    @pytest.mark.parametrize("typ", ["logout+jwt", "application/logout+jwt", "Logout+JWT", "JWT", "application/jwt"])
    def test_typ_is_compared_as_a_media_type(self, rsa_key, typ):
        assert _verify(_sign(rsa_key, _claims(), typ=typ), _jwks(rsa_key))["jti"] == "jti-1"

    def test_a_token_with_only_a_sid_is_accepted(self, rsa_key):
        claims = _verify(_sign(rsa_key, _claims(sub=None)), _jwks(rsa_key))

        assert "sub" not in claims

    def test_a_token_with_only_a_sub_is_accepted(self, rsa_key):
        claims = _verify(_sign(rsa_key, _claims(sid=None)), _jwks(rsa_key))

        assert "sid" not in claims

    def test_an_audience_list_naming_this_client_and_authorized_to_it_is_accepted(self, rsa_key):
        claims = _verify(_sign(rsa_key, _claims(aud=[AUD, "other"], azp=AUD)), _jwks(rsa_key))

        assert claims["azp"] == AUD

    def test_an_expiry_within_the_clock_leeway_is_accepted(self, rsa_key):
        now = int(time.time())
        token = _sign(rsa_key, _claims(iat=now - 300, exp=now - id_token_service.ID_TOKEN_CLOCK_LEEWAY_SECONDS + 10))

        assert _verify(token, _jwks(rsa_key))["jti"] == "jti-1"


class TestRefusedLogoutTokens:
    def test_a_token_signed_by_another_key_is_refused(self, rsa_key):
        other = RSAKey.generate_key(2048, parameters={"kid": KID})

        assert "signature" in _refused(_sign(other, _claims()), _jwks(rsa_key)).detail.lower()

    def test_an_unknown_key_is_refused_after_the_key_set_is_fetched_again(self, rsa_key):
        fetches: list[bool] = []

        def fetch(_uri, refresh=False):
            fetches.append(refresh)
            return {"keys": []}

        with pytest.raises(core_exceptions.UnauthenticatedError):
            id_token_service.verify_logout_token(fetch, _sign(rsa_key, _claims()), JWKS_URI, ISS, AUD)

        assert fetches == [False, True]

    @pytest.mark.parametrize("alg", ["none", "HS256"])
    def test_an_algorithm_outside_the_asymmetric_allow_list_is_refused(self, rsa_key, alg):
        header = base64.urlsafe_b64encode(json.dumps({"alg": alg}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps(_claims()).encode()).decode().rstrip("=")

        refusal = _refused(f"{header}.{payload}.", _jwks(rsa_key))

        assert "unsupported signature algorithm" in refusal.detail.lower()

    @pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c.d.e", "!!!.e30.sig", "W10.e30.sig"])
    def test_a_malformed_or_encrypted_token_is_refused(self, rsa_key, token):
        assert "format" in _refused(token, _jwks(rsa_key)).detail.lower()

    @pytest.mark.parametrize("typ", ["at+jwt", "id_token+jwt", "application/json"])
    def test_another_typ_is_refused(self, rsa_key, typ):
        assert "type" in _refused(_sign(rsa_key, _claims(), typ=typ), _jwks(rsa_key)).detail.lower()

    def test_another_issuer_is_refused(self, rsa_key):
        _refused(_sign(rsa_key, _claims(iss="https://evil.example.com")), _jwks(rsa_key))

    def test_another_audience_is_refused(self, rsa_key):
        _refused(_sign(rsa_key, _claims(aud="someone-else")), _jwks(rsa_key))

    def test_an_authorized_party_naming_another_client_is_refused(self, rsa_key):
        _refused(_sign(rsa_key, _claims(aud=[AUD, "other"], azp="other")), _jwks(rsa_key))

    def test_several_audiences_without_an_authorized_party_are_refused(self, rsa_key):
        _refused(_sign(rsa_key, _claims(aud=[AUD, "other"])), _jwks(rsa_key))

    @pytest.mark.parametrize("claim", ["iss", "aud", "iat", "exp", "jti", "events"])
    def test_a_missing_required_claim_is_refused(self, rsa_key, claim):
        _refused(_sign(rsa_key, _claims(**{claim: None})), _jwks(rsa_key))

    def test_an_expired_token_is_refused(self, rsa_key):
        now = int(time.time())
        token = _sign(rsa_key, _claims(iat=now - 600, exp=now - id_token_service.ID_TOKEN_CLOCK_LEEWAY_SECONDS - 30))

        assert "expired" in _refused(token, _jwks(rsa_key)).detail.lower()

    def test_a_token_issued_in_the_future_is_refused(self, rsa_key):
        now = int(time.time())
        _refused(_sign(rsa_key, _claims(iat=now + 600, exp=now + 900)), _jwks(rsa_key))

    def test_a_token_naming_neither_subject_nor_session_is_refused(self, rsa_key):
        refusal = _refused(_sign(rsa_key, _claims(sub=None, sid=None)), _jwks(rsa_key))

        assert "sub" in refusal.detail and "sid" in refusal.detail

    @pytest.mark.parametrize("value", ["", 7, ["a"], "x" * 256])
    def test_a_sid_that_is_not_a_bounded_string_is_refused(self, rsa_key, value):
        _refused(_sign(rsa_key, _claims(sid=value)), _jwks(rsa_key))

    @pytest.mark.parametrize("value", ["", 7, "x" * 501])
    def test_a_sub_that_is_not_a_bounded_string_is_refused(self, rsa_key, value):
        _refused(_sign(rsa_key, _claims(sub=value)), _jwks(rsa_key))

    def test_a_jti_that_is_not_a_string_is_refused(self, rsa_key):
        _refused(_sign(rsa_key, _claims(jti=7)), _jwks(rsa_key))

    @pytest.mark.parametrize(
        "events",
        [
            {"http://schemas.openid.net/event/other": {}},
            {EVENT: "yes"},
            {EVENT: None},
            [EVENT],
            EVENT,
        ],
    )
    def test_events_without_the_logout_member_as_an_object_are_refused(self, rsa_key, events):
        assert "events" in _refused(_sign(rsa_key, _claims(events=events)), _jwks(rsa_key)).detail

    def test_a_token_with_a_nonce_is_refused(self, rsa_key):
        assert "nonce" in _refused(_sign(rsa_key, _claims(nonce="n")), _jwks(rsa_key)).detail
