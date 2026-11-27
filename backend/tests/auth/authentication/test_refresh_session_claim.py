"""The session id of a refresh token is read as a UUID, and a claim that is not one is an invalid token."""

import uuid
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.dependencies as authentication_dependencies

_SESSION_ID = uuid.UUID(int=7)


def _token_manager(sid):
    manager = MagicMock()
    manager.get_token_claim.return_value = sid
    return manager


def test_a_refresh_sid_is_read_as_a_uuid():
    result = authentication_dependencies.get_sid_from_refresh_token("token", _token_manager(str(_SESSION_ID)))

    assert result == _SESSION_ID


@pytest.mark.parametrize("sid", ["session-1", "", "../1", 7, None])
def test_a_refresh_sid_that_is_not_a_uuid_is_an_invalid_token(sid):
    with pytest.raises(core_exceptions.InvalidTokenError):
        authentication_dependencies.get_sid_from_refresh_token("token", _token_manager(sid))
