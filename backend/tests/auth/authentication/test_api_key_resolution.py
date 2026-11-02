"""An API key stored in the database resolves to its owner's principal."""

import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.utils as api_keys_utils
import modules.auth.authentication.principal_service as principal_service
from tests._helpers.db import create_sqlite_session_factory, ensure_user

_USER_ID = 5


@pytest.fixture
def session_factory():
    factory = create_sqlite_session_factory()
    ensure_user(factory, _USER_ID)
    yield factory
    factory.kw["bind"].dispose()


def _store_key(factory, raw_key: str) -> api_keys_schema.UsersApiKeyRead:
    scopes = ["activities:upload"]
    with factory() as db:
        stored = api_keys_crud.create_api_key(
            _USER_ID,
            api_keys_schema.UsersApiKeyCreate(name="CLI", scopes=scopes),
            raw_key,
            api_keys_utils.hash_api_key(raw_key),
            api_keys_utils.scopes_to_json(scopes),
            db,
        )
        db.commit()
    return stored


class TestResolveFromApiKey:
    def test_a_stored_key_resolves_to_its_owner(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        stored = _store_key(session_factory, raw_key)

        with session_factory() as db:
            principal = principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        assert principal.user_id == _USER_ID
        assert principal.credential.api_key_id == stored.id
        assert principal.scopes == frozenset({"activities:upload"})

    def test_a_key_that_is_not_stored_is_refused(self, session_factory):
        _store_key(session_factory, api_keys_utils.generate_api_key())

        with session_factory() as db, pytest.raises(core_exceptions.UnauthenticatedError):
            principal_service.resolve_from_api_key(api_keys_utils.generate_api_key(), "/api/v1/x", "127.0.0.1", db)
