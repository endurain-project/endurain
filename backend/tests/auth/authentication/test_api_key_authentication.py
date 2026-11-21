"""An API key authenticates its owner with the scopes it holds; every other key is refused alike and audited."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import sqlalchemy as sa

import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.constants as authentication_constants
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.principal_service as principal_service
import modules.auth.authentication.subscribers as authentication_subscribers
import modules.users.users.models as users_models
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user

_ROUTE = "/api/v1/health/weight"
_READ = [api_keys_constants.ApiKeyScope.HEALTH_READ]


def _holder(app, committed_sessions, *, expires_at=None, scopes=None):
    with committed_sessions() as db:
        user = make_user(db)
        key, raw = make_api_key(db, user, scopes=scopes or _READ, expires_at=expires_at)
        db.commit()
    return key_client(app, user, key, raw)


def _refusals(sessions):
    return audit_rows(sessions, authentication_audit_actions.API_KEY_AUTHENTICATE)


def _set(sessions, key_id: uuid.UUID, **values) -> None:
    with sessions() as db:
        db.execute(
            sa.update(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.id == key_id).values(**values)
        )
        db.commit()


class TestAcceptedKey:
    def test_a_stored_key_authenticates_its_owner_and_writes_no_refusal(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)

        response = holder.client.get(_ROUTE)

        assert response.status_code == 200
        assert _refusals(committed_sessions) == []

    def test_a_key_does_not_open_a_route_whose_scope_it_lacks(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, scopes=[api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD])

        assert holder.client.get(_ROUTE).status_code == 403

    def test_a_key_resolves_to_its_owner_with_its_own_scopes(self, db):
        user = make_user(db)
        key, raw = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD])

        principal = principal_service.resolve_from_api_key(raw, "/api/v1/x", "127.0.0.1", db)

        assert principal.user_id == user.id
        assert principal.credential.api_key_id == key.id
        assert principal.scopes == frozenset({"activities:upload"})

    def test_a_key_holds_no_scope_its_owners_role_lacks(self, db):
        user = make_user(db)
        key, raw = make_api_key(db, user, scopes=_READ)
        db.execute(
            sa.update(api_keys_models.UsersApiKeys)
            .where(api_keys_models.UsersApiKeys.id == key.id)
            .values(scopes='["health:read", "server:admin"]')
        )
        db.flush()

        principal = principal_service.resolve_from_api_key(raw, "/api/v1/x", "127.0.0.1", db)

        assert principal.scopes == frozenset({"health:read"})


class TestRefusedKey:
    def test_an_unknown_key_is_a_401_audited_as_a_failure_with_no_target(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)
        stranger = key_client(app, holder.user, holder.key, "x" * 43)

        response = stranger.client.get(_ROUTE)

        assert response.status_code == 401
        (row,) = _refusals(committed_sessions)
        assert (row.outcome, row.target_id, row.details["reason"]) == ("failure", None, "unknown_key")

    def test_a_revoked_key_is_a_failure_that_targets_the_key(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)
        _set(committed_sessions, holder.key.id, is_active=False)

        response = holder.client.get(_ROUTE)

        assert response.status_code == 401
        (row,) = _refusals(committed_sessions)
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
            "failure",
            "api_key",
            str(holder.key.id),
            str(holder.user.id),
        )
        assert row.details["reason"] == "revoked"

    def test_an_expired_key_is_a_failure_that_targets_the_key(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, expires_at=datetime.now(UTC) - timedelta(days=1))

        response = holder.client.get(_ROUTE)

        assert response.status_code == 401
        (row,) = _refusals(committed_sessions)
        assert (row.outcome, row.target_id, row.details["reason"]) == ("failure", str(holder.key.id), "expired")

    def test_a_valid_key_of_an_inactive_owner_is_denied_with_a_401(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == holder.user.id).values(active=False)
            )
            db.commit()

        response = holder.client.get(_ROUTE)

        assert response.status_code == 401
        (row,) = _refusals(committed_sessions)
        assert (row.outcome, row.target_id, row.details["reason"]) == ("denied", str(holder.key.id), "owner_inactive")

    def test_a_refusal_never_records_the_key(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)
        _set(committed_sessions, holder.key.id, is_active=False)

        holder.client.get(_ROUTE)

        (row,) = _refusals(committed_sessions)
        assert holder.raw_key not in repr(row) and holder.key.key_prefix not in repr(row)


class TestLastUsedStamp:
    """A key's use is announced at most once per interval, so reading data does not write a row on every request."""

    def _last_used(self, sessions, key_id):
        with sessions() as db:
            return db.get(api_keys_models.UsersApiKeys, key_id).last_used_at

    def test_a_key_never_used_is_announced_and_its_use_recorded_by_the_subscriber(
        self, app, committed_sessions, published
    ):
        events = published(authentication_events.API_KEY_USED)
        authentication_subscribers.register_bus_subscribers(jasil_runtime.get_active_platform().events)
        holder = _holder(app, committed_sessions)

        holder.client.get(_ROUTE)

        assert [e.payload for e in events] == [{"api_key_id": str(holder.key.id)}]
        assert self._last_used(committed_sessions, holder.key.id) is not None

    def test_a_key_stamped_within_the_interval_is_not_announced_again(self, app, committed_sessions, published):
        holder = _holder(app, committed_sessions)
        recent = datetime.now(UTC) - authentication_constants.API_KEY_LAST_USED_INTERVAL / 2
        _set(committed_sessions, holder.key.id, last_used_at=recent)
        events = published(authentication_events.API_KEY_USED)

        holder.client.get(_ROUTE)

        assert events == []

    def test_a_key_stamped_longer_ago_than_the_interval_is_announced(self, app, committed_sessions, published):
        holder = _holder(app, committed_sessions)
        stale = datetime.now(UTC) - authentication_constants.API_KEY_LAST_USED_INTERVAL - timedelta(seconds=1)
        _set(committed_sessions, holder.key.id, last_used_at=stale)
        events = published(authentication_events.API_KEY_USED)

        holder.client.get(_ROUTE)

        assert len(events) == 1
