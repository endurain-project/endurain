"""The session id of a refresh token is read as a UUID, and a claim that is not one is an invalid token."""

import uuid
from datetime import timedelta

import pytest
from joserfc import jwt
from joserfc.jwk import OctKey

import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.authentication.dependencies as authentication_dependencies
from modules.auth.constants import ClientType
from modules.users.users.schema import UserAccessType, UserRead

_REFRESH_KEY = "refresh-key-for-testing-only-min-32-chars!"
_SESSION_ID = uuid.UUID(int=7)
_MANAGER = access_tokens_service.TokenManager(
    access_keys=["access-key-for-testing-only-min-32-chars!"], refresh_keys=[_REFRESH_KEY]
)
_USER = UserRead(
    id=uuid.UUID(int=5),
    name="User",
    username="user",
    email="user@example.com",
    access_type=UserAccessType.REGULAR.value,
    active=True,
)


def _refresh_token_with_sid(sid: object) -> str:
    """Sign the claims of a genuine refresh token again, with ``sid`` as the session claim."""
    _, genuine = _MANAGER.create_token(
        _SESSION_ID, _USER, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(minutes=5)
    )
    claims = dict(_MANAGER.decode_token(genuine, access_tokens_service.TokenType.REFRESH).claims) | {"sid": sid}
    header = {"alg": "HS256", "typ": "rt+jwt", "kid": core_jwt_keys.key_id(_REFRESH_KEY)}
    return jwt.encode(header, claims, OctKey.import_key(_REFRESH_KEY))


def test_a_refresh_sid_is_read_as_a_uuid():
    token = _refresh_token_with_sid(str(_SESSION_ID))

    assert authentication_dependencies.get_sid_from_refresh_token(token, _MANAGER) == _SESSION_ID


@pytest.mark.parametrize("sid", ["session-1", "", "../1", 7, None])
def test_a_refresh_sid_that_is_not_a_uuid_is_an_invalid_token(sid):
    token = _refresh_token_with_sid(sid)

    with pytest.raises(core_exceptions.InvalidTokenError):
        authentication_dependencies.get_sid_from_refresh_token(token, _MANAGER)
