"""The audience, client and lifetime claims of Endurain's own tokens (RFC 9068, RFC 8725)."""

import time
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from joserfc import jwt
from joserfc.jwk import OctKey

import core.config as core_config
import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import core.problem_details as core_problem_details
import modules.auth.access_tokens.service as auth_token_manager
from modules.auth.constants import ClientType
from modules.users.users.schema import UserAccessType, UserRead

_ACCESS_KEY = "claims-access-key-for-testing-only-min-32-chars"
_REFRESH_KEY = "claims-refresh-key-for-testing-only-min-32-chars"
_ACCESS = auth_token_manager.TokenType.ACCESS
_REFRESH = auth_token_manager.TokenType.REFRESH
_KEYS = {_ACCESS: _ACCESS_KEY, _REFRESH: _REFRESH_KEY}
_LEEWAY = core_jwt_keys.CLOCK_LEEWAY_SECONDS


@pytest.fixture
def manager() -> auth_token_manager.TokenManager:
    return auth_token_manager.TokenManager(access_keys=[_ACCESS_KEY], refresh_keys=[_REFRESH_KEY])


@pytest.fixture
def user() -> UserRead:
    return UserRead(
        id=1,
        name="User",
        username="user",
        email="user@test.com",
        access_type=UserAccessType.REGULAR.value,
        active=True,
    )


def _claims(manager, user, token_type, client_type=ClientType.WEB) -> dict:
    _, token = manager.create_token("sid", user, client_type, token_type, timedelta(minutes=5))
    return dict(manager.decode_token(token, token_type).claims)


def _sign(claims: dict, token_type) -> str:
    """Sign ``claims`` as a genuine token of ``token_type``: its key, ``kid`` and ``typ``."""
    key = _KEYS[token_type]
    header = {"alg": "HS256", "typ": token_type.header_type, "kid": core_jwt_keys.key_id(key)}
    return jwt.encode(header, claims, OctKey.import_key(key))


class TestAudience:
    def test_an_access_token_is_for_the_resource_server(self, manager, user):
        assert _claims(manager, user, _ACCESS)["aud"] == core_config.settings.ENDURAIN_HOST

    def test_a_refresh_token_is_for_the_refresh_endpoint(self, manager, user):
        assert _claims(manager, user, _REFRESH)["aud"] == (
            f"{core_config.settings.ENDURAIN_HOST}{core_config.ROOT_PATH}/auth/refresh"
        )

    def test_both_kinds_have_the_same_issuer(self, manager, user):
        assert _claims(manager, user, _ACCESS)["iss"] == _claims(manager, user, _REFRESH)["iss"]
        assert _claims(manager, user, _ACCESS)["iss"] == core_config.settings.ENDURAIN_HOST

    def test_the_refresh_audience_names_the_refresh_route_of_the_api(self):
        import api

        app = core_problem_details.ProblemDetailsFastAPI()
        app.include_router(api.router)
        audience = urlsplit(auth_token_manager.token_audience(_REFRESH))

        assert f"{audience.scheme}://{audience.netloc}" == core_config.settings.ENDURAIN_HOST
        assert app.openapi()["paths"][audience.path]["post"]["operationId"] == "refresh_token"

    @pytest.mark.parametrize(("token_type", "other"), [(_ACCESS, _REFRESH), (_REFRESH, _ACCESS)])
    def test_a_token_carrying_the_audience_of_the_other_kind_is_refused(self, manager, user, token_type, other):
        claims = _claims(manager, user, token_type) | {"aud": auth_token_manager.token_audience(other)}

        with pytest.raises(core_exceptions.InvalidTokenError, match="invalid claims"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_for_another_audience_is_refused(self, manager, user, token_type):
        claims = _claims(manager, user, token_type) | {"aud": "https://elsewhere.example"}

        with pytest.raises(core_exceptions.InvalidTokenError, match="invalid claims"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)


class TestClientId:
    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    @pytest.mark.parametrize("client_type", list(ClientType))
    def test_the_token_names_the_client_it_was_issued_for(self, manager, user, token_type, client_type):
        assert _claims(manager, user, token_type, client_type)["client_id"] == client_type.value

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_without_a_client_is_refused(self, manager, user, token_type):
        claims = _claims(manager, user, token_type)
        del claims["client_id"]

        with pytest.raises(core_exceptions.InvalidTokenError, match="missing required claims"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_for_an_unknown_client_is_refused(self, manager, user, token_type):
        claims = _claims(manager, user, token_type) | {"client_id": "desktop"}

        with pytest.raises(core_exceptions.InvalidTokenError, match="invalid claims"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)


class TestClockLeeway:
    """Replicas' clocks differ by a little; a token is judged with a leeway of that size, and no more."""

    def test_the_leeway_is_a_minute(self):
        assert _LEEWAY == 60

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_issued_by_a_clock_a_little_ahead_verifies(self, manager, user, token_type):
        ahead = int(time.time()) + 5
        claims = _claims(manager, user, token_type) | {"iat": ahead, "nbf": ahead}

        manager.validate_token_expiration(_sign(claims, token_type), token_type)

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_that_expired_a_moment_ago_verifies(self, manager, user, token_type):
        claims = _claims(manager, user, token_type) | {"exp": int(time.time()) - 5}

        manager.validate_token_expiration(_sign(claims, token_type), token_type)

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_from_beyond_the_leeway_ahead_is_refused(self, manager, user, token_type):
        ahead = int(time.time()) + _LEEWAY + 30
        claims = _claims(manager, user, token_type) | {"iat": ahead, "nbf": ahead}

        with pytest.raises(core_exceptions.InvalidTokenError, match="not valid yet"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)

    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_expired_beyond_the_leeway_is_refused(self, manager, user, token_type):
        claims = _claims(manager, user, token_type) | {"exp": int(time.time()) - _LEEWAY - 30}

        with pytest.raises(core_exceptions.InvalidTokenError, match="expired"):
            manager.validate_token_expiration(_sign(claims, token_type), token_type)

    def test_not_before_is_the_issue_time(self, manager, user):
        claims = _claims(manager, user, _ACCESS)

        assert claims["nbf"] == claims["iat"]
