"""The JOSE header names the kind of token and the key that signed it, and a key list lets the key rotate."""

from datetime import timedelta

import pytest
from joserfc import jwt
from joserfc.jwk import OctKey

import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import modules.auth.access_tokens.service as auth_token_manager
from modules.users.users.schema import UserAccessType, UsersRead

_NEW = "new-secret-key-for-testing-only-min-32-chars"
_OLD = "old-secret-key-for-testing-only-min-32-chars"
_STRANGER = "stranger-secret-key-for-testing-only-32-chars"
_ACCESS = auth_token_manager.TokenType.ACCESS
_REFRESH = auth_token_manager.TokenType.REFRESH


@pytest.fixture
def user() -> UsersRead:
    return UsersRead(
        id=1,
        name="User",
        username="user",
        email="user@test.com",
        access_type=UserAccessType.REGULAR.value,
        active=True,
    )


def _token(manager: auth_token_manager.TokenManager, user: UsersRead, token_type=_ACCESS) -> str:
    return manager.create_token("sid", user, token_type, timedelta(minutes=5))[1]


class TestHeader:
    def test_an_access_token_is_typed_at_jwt(self, token_manager, user):
        header = token_manager.decode_token(_token(token_manager, user)).header

        assert header["typ"] == "at+jwt"
        assert header["alg"] == "HS256"

    def test_a_refresh_token_is_typed_rt_jwt(self, token_manager, user):
        assert token_manager.decode_token(_token(token_manager, user, _REFRESH)).header["typ"] == "rt+jwt"

    def test_the_header_names_the_signing_key(self, token_manager, user):
        header = token_manager.decode_token(_token(token_manager, user)).header

        assert header["kid"] == core_jwt_keys.key_id(token_manager.secret_key)

    def test_the_kind_is_no_longer_a_payload_claim(self, token_manager, user):
        assert "typ" not in token_manager.decode_token(_token(token_manager, user)).claims

    def test_a_refresh_token_is_not_an_access_token(self, token_manager, user):
        with pytest.raises(core_exceptions.InvalidTokenError):
            token_manager.validate_token_expiration(_token(token_manager, user, _REFRESH), _ACCESS)

    def test_an_access_token_is_not_a_refresh_token(self, token_manager, user):
        with pytest.raises(core_exceptions.InvalidTokenError):
            token_manager.validate_token_expiration(_token(token_manager, user), _REFRESH)

    def test_a_token_without_a_header_type_is_refused(self, token_manager, user):
        claims = token_manager.decode_token(_token(token_manager, user)).claims
        key = OctKey.import_key(token_manager.secret_key)
        untyped = jwt.encode({"alg": "HS256", "kid": core_jwt_keys.key_id(token_manager.secret_key)}, claims, key)

        with pytest.raises(core_exceptions.InvalidTokenError):
            token_manager.validate_token_expiration(untyped, _ACCESS)


class TestScopeClaim:
    def test_the_scope_is_a_space_separated_string(self, token_manager, user):
        scope = token_manager.get_token_claim(_token(token_manager, user), "scope")

        assert isinstance(scope, str)
        assert "profile" in scope.split()


class TestKeyRotation:
    def test_a_token_signed_with_a_listed_old_key_still_verifies(self, user):
        old = auth_token_manager.TokenManager(secret_key=_OLD)
        rotated = auth_token_manager.TokenManager(secret_key=_NEW, previous_keys=[_OLD])

        rotated.validate_token_expiration(_token(old, user), _ACCESS)

    def test_new_tokens_are_signed_with_the_first_key(self, user):
        rotated = auth_token_manager.TokenManager(secret_key=_NEW, previous_keys=[_OLD])
        old = auth_token_manager.TokenManager(secret_key=_OLD)
        token = _token(rotated, user)

        assert rotated.decode_token(token).header["kid"] == core_jwt_keys.key_id(_NEW)
        with pytest.raises(core_exceptions.InvalidTokenError):
            old.validate_token_expiration(token, _ACCESS)

    def test_a_key_that_left_the_list_no_longer_verifies(self, user):
        old = auth_token_manager.TokenManager(secret_key=_OLD)
        new_only = auth_token_manager.TokenManager(secret_key=_NEW)

        with pytest.raises(core_exceptions.InvalidTokenError):
            new_only.validate_token_expiration(_token(old, user), _ACCESS)

    def test_a_key_outside_the_list_is_refused(self, user):
        stranger = auth_token_manager.TokenManager(secret_key=_STRANGER)
        rotated = auth_token_manager.TokenManager(secret_key=_NEW, previous_keys=[_OLD])

        with pytest.raises(core_exceptions.InvalidTokenError):
            rotated.validate_token_expiration(_token(stranger, user), _ACCESS)

    def test_a_token_naming_another_key_is_not_tried_against_every_key(self, user):
        """The ``kid`` selects the key: a signature made with a listed key under another key's id fails."""
        old = auth_token_manager.TokenManager(secret_key=_OLD)
        claims = old.decode_token(_token(old, user)).claims
        forged = jwt.encode(
            {"alg": "HS256", "typ": "at+jwt", "kid": core_jwt_keys.key_id(_NEW)}, claims, OctKey.import_key(_OLD)
        )
        rotated = auth_token_manager.TokenManager(secret_key=_NEW, previous_keys=[_OLD])

        with pytest.raises(core_exceptions.InvalidTokenError):
            rotated.validate_token_expiration(forged, _ACCESS)
