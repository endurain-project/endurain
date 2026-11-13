"""The JOSE header names the kind of token and the key that signed it, and a key list lets the key rotate."""

import uuid
from datetime import timedelta

import pytest
from joserfc import jwt
from joserfc.jwk import OctKey

import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import core.key_derivation as core_key_derivation
import modules.auth.access_tokens.service as auth_token_manager
from modules.auth.constants import ClientType
from modules.users.users.schema import UserAccessType, UserRead

_USER_ID = uuid.UUID(int=1)
_SESSION_ID = uuid.UUID(int=0x5E55)

_NEW = "new-secret-key-for-testing-only-min-32-chars"
_OLD = "old-secret-key-for-testing-only-min-32-chars"
_NEW_REFRESH = "new-refresh-key-for-testing-only-min-32-chars"
_OLD_REFRESH = "old-refresh-key-for-testing-only-min-32-chars"
_STRANGER = "stranger-secret-key-for-testing-only-32-chars"
_ACCESS = auth_token_manager.TokenType.ACCESS
_REFRESH = auth_token_manager.TokenType.REFRESH


@pytest.fixture
def user() -> UserRead:
    return UserRead(
        id=_USER_ID,
        name="User",
        username="user",
        email="user@test.com",
        access_type=UserAccessType.REGULAR.value,
        active=True,
    )


def _manager(access: list[str], refresh: list[str] | None = None) -> auth_token_manager.TokenManager:
    return auth_token_manager.TokenManager(access_keys=access, refresh_keys=refresh or [_NEW_REFRESH])


def _token(manager: auth_token_manager.TokenManager, user: UserRead, token_type=_ACCESS) -> str:
    return manager.create_token(_SESSION_ID, user, ClientType.WEB, token_type, timedelta(minutes=5))[1]


def _resign(manager, token: str, token_type, *, key: str, typ: str) -> str:
    """Return the claims of a genuine token signed again with ``key`` under its ``kid`` and with header ``typ``."""
    claims = manager.decode_token(token, token_type).claims
    return jwt.encode({"alg": "HS256", "typ": typ, "kid": core_jwt_keys.key_id(key)}, claims, OctKey.import_key(key))


class TestHeader:
    def test_an_access_token_is_typed_at_jwt(self, token_manager, user):
        header = token_manager.decode_token(_token(token_manager, user), _ACCESS).header

        assert header["typ"] == "at+jwt"
        assert header["alg"] == "HS256"

    def test_a_refresh_token_is_typed_rt_jwt(self, token_manager, user):
        assert token_manager.decode_token(_token(token_manager, user, _REFRESH), _REFRESH).header["typ"] == "rt+jwt"

    def test_the_header_names_the_signing_key_of_each_kind(self, user):
        manager = _manager([_NEW])

        assert manager.decode_token(_token(manager, user), _ACCESS).header["kid"] == core_jwt_keys.key_id(_NEW)
        assert manager.decode_token(_token(manager, user, _REFRESH), _REFRESH).header["kid"] == core_jwt_keys.key_id(
            _NEW_REFRESH
        )

    def test_the_kind_is_no_longer_a_payload_claim(self, token_manager, user):
        assert "typ" not in token_manager.decode_token(_token(token_manager, user), _ACCESS).claims

    def test_a_refresh_token_is_not_an_access_token(self, token_manager, user):
        with pytest.raises(core_exceptions.InvalidTokenError):
            token_manager.validate_token_expiration(_token(token_manager, user, _REFRESH), _ACCESS)

    def test_an_access_token_is_not_a_refresh_token(self, token_manager, user):
        with pytest.raises(core_exceptions.InvalidTokenError):
            token_manager.validate_token_expiration(_token(token_manager, user), _REFRESH)

    def test_a_token_without_a_header_type_is_refused(self, user):
        manager = _manager([_NEW])
        claims = manager.decode_token(_token(manager, user), _ACCESS).claims
        untyped = jwt.encode({"alg": "HS256", "kid": core_jwt_keys.key_id(_NEW)}, claims, OctKey.import_key(_NEW))

        with pytest.raises(core_exceptions.InvalidTokenError):
            manager.validate_token_expiration(untyped, _ACCESS)


class TestKeyPerKind:
    """Access and refresh tokens are signed with different keys, so a forged ``typ`` does not swap them."""

    def test_a_refresh_token_signed_with_the_access_key_is_refused(self, user):
        manager = _manager([_NEW])
        forged = _resign(manager, _token(manager, user, _REFRESH), _REFRESH, key=_NEW, typ="rt+jwt")

        with pytest.raises(core_exceptions.InvalidTokenError):
            manager.validate_token_expiration(forged, _REFRESH)

    def test_an_access_token_signed_with_the_refresh_key_is_refused(self, user):
        manager = _manager([_NEW])
        forged = _resign(manager, _token(manager, user), _ACCESS, key=_NEW_REFRESH, typ="at+jwt")

        with pytest.raises(core_exceptions.InvalidTokenError):
            manager.validate_token_expiration(forged, _ACCESS)

    def test_a_refresh_token_typed_as_an_access_token_is_refused(self, user):
        manager = _manager([_NEW])
        forged = _resign(manager, _token(manager, user, _REFRESH), _REFRESH, key=_NEW_REFRESH, typ="at+jwt")

        with pytest.raises(core_exceptions.InvalidTokenError):
            manager.validate_token_expiration(forged, _ACCESS)

    def test_the_refresh_key_is_derived_for_its_own_purpose(self):
        assert core_key_derivation.REFRESH_JWT != core_key_derivation.JWT
        assert core_key_derivation.derive_keys(core_key_derivation.REFRESH_JWT) == core_jwt_keys.REFRESH_SIGNING_KEYS
        assert set(core_jwt_keys.REFRESH_SIGNING_KEYS).isdisjoint(core_jwt_keys.SIGNING_KEYS)

    def test_the_server_manager_signs_each_kind_with_its_own_derived_key(self, user):
        manager = auth_token_manager.get_token_manager()

        access = manager.decode_token(_token(manager, user), _ACCESS)
        refresh = manager.decode_token(_token(manager, user, _REFRESH), _REFRESH)

        assert access.header["kid"] == core_jwt_keys.key_id(core_jwt_keys.SIGNING_KEYS[0])
        assert refresh.header["kid"] == core_jwt_keys.key_id(core_jwt_keys.REFRESH_SIGNING_KEYS[0])

    @pytest.mark.parametrize(("access", "refresh"), [([], [_NEW_REFRESH]), ([_NEW], [])])
    def test_each_kind_needs_a_key(self, access, refresh):
        with pytest.raises(ValueError, match="key"):
            auth_token_manager.TokenManager(access_keys=access, refresh_keys=refresh)


class TestScopeClaim:
    def test_the_scope_is_a_space_separated_string(self, token_manager, user):
        scope = token_manager.get_token_claim(_token(token_manager, user), "scope", _ACCESS)

        assert isinstance(scope, str)
        assert "account" in scope.split()


class TestKeyRotation:
    @pytest.mark.parametrize("token_type", [_ACCESS, _REFRESH])
    def test_a_token_signed_with_a_listed_old_key_still_verifies(self, user, token_type):
        old = _manager([_OLD], [_OLD_REFRESH])
        rotated = _manager([_NEW, _OLD], [_NEW_REFRESH, _OLD_REFRESH])

        rotated.validate_token_expiration(_token(old, user, token_type), token_type)

    @pytest.mark.parametrize(("token_type", "new_key"), [(_ACCESS, _NEW), (_REFRESH, _NEW_REFRESH)])
    def test_new_tokens_are_signed_with_the_first_key(self, user, token_type, new_key):
        rotated = _manager([_NEW, _OLD], [_NEW_REFRESH, _OLD_REFRESH])
        old = _manager([_OLD], [_OLD_REFRESH])
        token = _token(rotated, user, token_type)

        assert rotated.decode_token(token, token_type).header["kid"] == core_jwt_keys.key_id(new_key)
        with pytest.raises(core_exceptions.InvalidTokenError):
            old.validate_token_expiration(token, token_type)

    def test_an_old_access_key_does_not_verify_a_refresh_token(self, user):
        """Each kind rotates over its own keys: an old access key is not a refresh key."""
        old = _manager([_OLD], [_OLD_REFRESH])
        rotated = _manager([_NEW, _OLD], [_NEW_REFRESH])
        forged = _resign(old, _token(old, user, _REFRESH), _REFRESH, key=_OLD, typ="rt+jwt")

        with pytest.raises(core_exceptions.InvalidTokenError):
            rotated.validate_token_expiration(forged, _REFRESH)

    def test_a_key_that_left_the_list_no_longer_verifies(self, user):
        old = _manager([_OLD])
        new_only = _manager([_NEW])

        with pytest.raises(core_exceptions.InvalidTokenError):
            new_only.validate_token_expiration(_token(old, user), _ACCESS)

    def test_a_key_outside_the_list_is_refused(self, user):
        stranger = _manager([_STRANGER])
        rotated = _manager([_NEW, _OLD])

        with pytest.raises(core_exceptions.InvalidTokenError):
            rotated.validate_token_expiration(_token(stranger, user), _ACCESS)

    def test_a_token_naming_another_key_is_not_tried_against_every_key(self, user):
        """The ``kid`` selects the key: a signature made with a listed key under another key's id fails."""
        old = _manager([_OLD])
        claims = old.decode_token(_token(old, user), _ACCESS).claims
        forged = jwt.encode(
            {"alg": "HS256", "typ": "at+jwt", "kid": core_jwt_keys.key_id(_NEW)}, claims, OctKey.import_key(_OLD)
        )
        rotated = _manager([_NEW, _OLD])

        with pytest.raises(core_exceptions.InvalidTokenError):
            rotated.validate_token_expiration(forged, _ACCESS)
