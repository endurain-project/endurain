"""An API key stored in the database resolves to its owner's principal."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.utils as api_keys_utils
import modules.auth.authentication.constants as authentication_constants
import modules.auth.authentication.principal_service as principal_service
import modules.server_settings.contracts as server_settings_contracts
from tests._helpers.db import create_sqlite_session_factory, ensure_user

_USER_ID = uuid.UUID(int=5)


class _NaiveUtcDatetime(datetime):
    """The clock as SQLite hands timestamps back: UTC without an offset."""

    @classmethod
    def now(cls, tz=None):
        return super().now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _sqlite_naive_clock():
    with patch.object(principal_service, "datetime", _NaiveUtcDatetime):
        yield


@pytest.fixture(autouse=True)
def _mfa_not_required():
    with patch.object(
        principal_service.server_settings_integration,
        "get_access_policy",
        return_value=MagicMock(require_mfa=server_settings_contracts.RequireMfa.OFF),
    ):
        yield


@pytest.fixture
def session_factory():
    factory = create_sqlite_session_factory()
    ensure_user(factory, _USER_ID)
    yield factory
    factory.kw["bind"].dispose()


def _store_key(factory, raw_key: str) -> api_keys_schema.UserApiKeyRead:
    scopes = ["activities:upload"]
    with factory() as db:
        stored = api_keys_crud.create_api_key(
            _USER_ID,
            api_keys_schema.UserApiKeyCreate(step_up={"current_password": "pw"}, name="CLI", scopes=scopes),
            raw_key,
            api_keys_utils.hash_api_key(raw_key),
            api_keys_utils.scopes_to_json(scopes),
            datetime.now(UTC) + timedelta(days=30),
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

    def test_a_key_of_an_account_that_must_enrol_mfa_carries_it(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        _store_key(session_factory, raw_key)

        with (
            session_factory() as db,
            patch.object(
                principal_service.server_settings_integration,
                "get_access_policy",
                return_value=MagicMock(require_mfa=server_settings_contracts.RequireMfa.EVERYONE),
            ),
        ):
            principal = principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        assert principal.mfa_enrolment_required is True

    def test_a_key_holds_no_scope_its_owners_role_lacks(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        _store_key(session_factory, raw_key)

        with (
            session_factory() as db,
            patch.object(principal_service.access_tokens_integration, "scopes_for_access_type", return_value=[]),
        ):
            principal = principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        assert principal.scopes == frozenset()

    def test_a_key_that_is_not_stored_is_refused(self, session_factory):
        _store_key(session_factory, api_keys_utils.generate_api_key())

        with session_factory() as db, pytest.raises(core_exceptions.UnauthenticatedError):
            principal_service.resolve_from_api_key(api_keys_utils.generate_api_key(), "/api/v1/x", "127.0.0.1", db)


def _set_last_used(factory, api_key_id: str, last_used_at: datetime) -> None:
    with factory() as db:
        db.get(api_keys_models.UsersApiKeys, api_key_id).last_used_at = last_used_at
        db.commit()


class TestLastUsedStamp:
    """A key's use is stamped at most once per interval, so reading data does not write a row on every request."""

    _PUBLISH = "modules.auth.authentication.principal_service.authentication_event_publishers.publish_api_key_used"

    def test_a_key_never_used_is_stamped(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        stored = _store_key(session_factory, raw_key)

        with session_factory() as db, patch(self._PUBLISH) as publish:
            principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        publish.assert_called_once_with(stored.id, db)

    def test_a_key_stamped_within_the_interval_is_not_stamped_again(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        stored = _store_key(session_factory, raw_key)
        recent = _NaiveUtcDatetime.now() - authentication_constants.API_KEY_LAST_USED_INTERVAL / 2
        _set_last_used(session_factory, stored.id, recent)

        with session_factory() as db, patch(self._PUBLISH) as publish:
            principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        publish.assert_not_called()

    def test_a_key_stamped_longer_ago_than_the_interval_is_stamped(self, session_factory):
        raw_key = api_keys_utils.generate_api_key()
        stored = _store_key(session_factory, raw_key)
        stale = _NaiveUtcDatetime.now() - authentication_constants.API_KEY_LAST_USED_INTERVAL - timedelta(seconds=1)
        _set_last_used(session_factory, stored.id, stale)

        with session_factory() as db, patch(self._PUBLISH) as publish:
            principal_service.resolve_from_api_key(raw_key, "/api/v1/x", "127.0.0.1", db)

        publish.assert_called_once_with(stored.id, db)
