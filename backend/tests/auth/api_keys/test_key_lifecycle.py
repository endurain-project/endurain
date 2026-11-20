"""An API key authenticates until it is revoked or expires, stamps its last use, and an account holds at most 25."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jasil.runtime
import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.constants as authentication_constants
import modules.auth.authentication.subscribers as authentication_subscribers
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_user

_API_KEYS = f"{core_config.ROOT_PATH}/profile/api-keys"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_SCOPES = [api_keys_constants.ApiKeyScope.ACCOUNT]
_STEP_UP = {"current_password": PASSWORD}
_LIMIT_TYPE = "urn:endurain:error:api-key-limit"


def _key_of(committed_sessions, app, **key_options):
    with committed_sessions() as db:
        user = make_user(db)
        key, raw_key = make_api_key(db, user, scopes=_SCOPES, **key_options)
        db.commit()
    return key_client(app, user, key, raw_key)


def _key_row(committed_sessions, key_id: uuid.UUID) -> api_keys_models.UsersApiKeys:
    with committed_sessions() as db:
        return db.scalars(
            sa.select(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.id == key_id)
        ).one()


def _set_last_used(committed_sessions, key_id: uuid.UUID, moment: datetime | None) -> None:
    with committed_sessions() as db:
        db.execute(
            sa.update(api_keys_models.UsersApiKeys)
            .where(api_keys_models.UsersApiKeys.id == key_id)
            .values(last_used_at=moment)
        )
        db.commit()


def _refusals(committed_sessions):
    rows = audit_rows(committed_sessions, authentication_audit_actions.API_KEY_AUTHENTICATE)
    return [(row.outcome, row.target_type, row.details["reason"]) for row in rows]


class TestRefusals:
    def test_an_active_key_is_served_as_its_owner(self, app, committed_sessions):
        holder = _key_of(committed_sessions, app)

        response = holder.client.get(_PROFILE)

        assert response.status_code == 200
        assert response.json()["id"] == str(holder.user.id)
        assert _refusals(committed_sessions) == []

    def test_a_key_that_is_not_stored_is_refused_and_audited_without_a_target(self, app, committed_sessions):
        response = TestClient(app, headers={"X-API-Key": "ek_not-a-stored-key"}).get(_PROFILE)

        assert response.status_code == 401
        assert _refusals(committed_sessions) == [("failure", None, "unknown_key")]

    def test_an_expired_key_is_refused_and_audited_against_the_key(self, app, committed_sessions):
        holder = _key_of(committed_sessions, app, expires_at=datetime.now(UTC) - timedelta(seconds=1))

        response = holder.client.get(_PROFILE)

        assert response.status_code == 401
        rows = audit_rows(committed_sessions, authentication_audit_actions.API_KEY_AUTHENTICATE)
        assert [(row.outcome, row.target_id, row.target_owner_id, row.details["reason"]) for row in rows] == [
            ("failure", str(holder.key.id), str(holder.user.id), "expired")
        ]
        assert _key_row(committed_sessions, holder.key.id).last_used_at is None

    def test_a_key_whose_owner_was_deactivated_is_refused_as_denied(self, app, committed_sessions):
        holder = _key_of(committed_sessions, app)
        with committed_sessions() as db:
            db.execute(sa.text("UPDATE users SET active = false WHERE id = :id"), {"id": holder.user.id})
            db.commit()

        response = holder.client.get(_PROFILE)

        assert response.status_code == 403
        assert _refusals(committed_sessions) == [("denied", "api_key", "owner_inactive")]


class TestRevocation:
    def test_a_revoked_key_is_refused_from_then_on_and_both_steps_are_audited(self, app, committed_sessions, sign_in):
        holder = _key_of(committed_sessions, app)
        owner = sign_in(holder.user)
        assert holder.client.get(_PROFILE).status_code == 200

        revoked = owner.client.post(f"{_API_KEYS}/{holder.key.id}/revoke")
        after = holder.client.get(_PROFILE)

        assert revoked.status_code == 204
        assert after.status_code == 401
        row = _key_row(committed_sessions, holder.key.id)
        assert (row.is_active, row.revoked_at is not None) == (False, True)
        assert _refusals(committed_sessions) == [("failure", "api_key", "revoked")]
        revokes = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_REVOKE)
        assert [(row.outcome, row.target_id) for row in revokes] == [("success", str(holder.key.id))]

    def test_another_user_cannot_revoke_the_key(self, app, committed_sessions, sign_in):
        holder = _key_of(committed_sessions, app)
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()

        response = sign_in(stranger).client.post(f"{_API_KEYS}/{holder.key.id}/revoke")

        assert response.status_code == 404
        assert holder.client.get(_PROFILE).status_code == 200


class TestKeyLimit:
    def _user_with_keys(self, committed_sessions, count: int):
        with committed_sessions() as db:
            user = make_user(db)
            for _ in range(count):
                make_api_key(db, user, scopes=_SCOPES)
            db.commit()
        return user

    def _create(self, client: TestClient):
        return client.post(_API_KEYS, json={"name": "new key", "scopes": ["account"], "step_up": _STEP_UP})

    def _active_keys(self, committed_sessions, user_id: uuid.UUID) -> int:
        with committed_sessions() as db:
            return db.scalar(
                sa.select(sa.func.count())
                .select_from(api_keys_models.UsersApiKeys)
                .where(api_keys_models.UsersApiKeys.user_id == user_id)
            )

    def test_the_key_after_the_last_free_slot_is_created_and_the_next_is_a_conflict(self, committed_sessions, sign_in):
        user = self._user_with_keys(committed_sessions, api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER - 1)
        owner = sign_in(user)

        created = self._create(owner.client)
        refused = self._create(owner.client)

        assert created.status_code == 201
        assert created.headers["Cache-Control"] == "no-store"
        assert refused.status_code == 409
        assert refused.json()["type"] == _LIMIT_TYPE
        assert self._active_keys(committed_sessions, user.id) == api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER
        creates = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_CREATE)
        assert len(creates) == 1

    def test_revoked_and_expired_keys_do_not_count_toward_the_limit(self, committed_sessions, sign_in):
        user = self._user_with_keys(committed_sessions, api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER)
        with committed_sessions() as db:
            db.execute(
                sa.update(api_keys_models.UsersApiKeys)
                .where(
                    api_keys_models.UsersApiKeys.id.in_(
                        sa.select(api_keys_models.UsersApiKeys.id)
                        .where(api_keys_models.UsersApiKeys.user_id == user.id)
                        .limit(1)
                    )
                )
                .values(is_active=False, revoked_at=datetime.now(UTC))
            )
            db.execute(
                sa.update(api_keys_models.UsersApiKeys)
                .where(
                    api_keys_models.UsersApiKeys.id.in_(
                        sa.select(api_keys_models.UsersApiKeys.id)
                        .where(api_keys_models.UsersApiKeys.user_id == user.id, api_keys_models.UsersApiKeys.is_active)
                        .limit(1)
                    )
                )
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            db.commit()
        owner = sign_in(user)

        assert self._create(owner.client).status_code == 201
        assert self._create(owner.client).status_code == 201
        assert self._create(owner.client).status_code == 409

    def test_two_simultaneous_creations_with_one_slot_left_create_one_key(self, app, committed_sessions, sign_in):
        user = self._user_with_keys(committed_sessions, api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER - 1)
        owner = sign_in(user)
        barrier = threading.Barrier(2)

        def create():
            client = TestClient(app, headers=dict(owner.client.headers))
            barrier.wait(timeout=10)
            return self._create(client)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result(timeout=60) for future in [pool.submit(create) for _ in range(2)]]

        assert sorted(response.status_code for response in responses) == [201, 409]
        assert self._active_keys(committed_sessions, user.id) == api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER

    def test_a_wrong_step_up_password_creates_no_key(self, committed_sessions, sign_in):
        user = self._user_with_keys(committed_sessions, 0)

        response = sign_in(user).client.post(
            _API_KEYS, json={"name": "new key", "scopes": ["account"], "step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert self._active_keys(committed_sessions, user.id) == 0


class TestLastUsed:
    def _recording(self):
        """Deliver the event a use publishes to the subscriber that stamps the key, as the running server does."""
        authentication_subscribers.register_bus_subscribers(jasil.runtime.get_active_platform().events)

    def test_the_first_use_stamps_the_key(self, app, committed_sessions):
        self._recording()
        holder = _key_of(committed_sessions, app)
        before = datetime.now(UTC)

        assert holder.client.get(_PROFILE).status_code == 200

        stamped = _key_row(committed_sessions, holder.key.id).last_used_at
        assert stamped is not None and before <= stamped <= datetime.now(UTC)

    def test_a_use_within_the_interval_does_not_stamp_again(self, app, committed_sessions):
        self._recording()
        holder = _key_of(committed_sessions, app)
        recent = datetime.now(UTC) - authentication_constants.API_KEY_LAST_USED_INTERVAL / 2
        _set_last_used(committed_sessions, holder.key.id, recent)

        assert holder.client.get(_PROFILE).status_code == 200

        assert _key_row(committed_sessions, holder.key.id).last_used_at == recent

    def test_a_use_after_the_interval_stamps_again(self, app, committed_sessions):
        self._recording()
        holder = _key_of(committed_sessions, app)
        stale = datetime.now(UTC) - authentication_constants.API_KEY_LAST_USED_INTERVAL - timedelta(seconds=1)
        _set_last_used(committed_sessions, holder.key.id, stale)

        assert holder.client.get(_PROFILE).status_code == 200

        stamped = _key_row(committed_sessions, holder.key.id).last_used_at
        assert stamped is not None and stamped > stale + authentication_constants.API_KEY_LAST_USED_INTERVAL
