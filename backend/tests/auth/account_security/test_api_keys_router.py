"""A user's own API keys, and an administrator's view and revocation of another user's keys."""

import uuid

import sqlalchemy as sa

import core.config as core_config
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
from tests._factories.account_security import deliver_notices, sent_to
from tests._factories.api_keys import make_api_key
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_admin, make_user

_API_KEYS = f"{core_config.ROOT_PATH}/profile/api-keys"
_USERS = f"{core_config.ROOT_PATH}/users"
_STEP_UP = {"current_password": PASSWORD}
_SCOPES = [api_keys_constants.ApiKeyScope.ACCOUNT]


def _key_row(committed_sessions, key_id: uuid.UUID) -> api_keys_models.UsersApiKeys | None:
    with committed_sessions() as db:
        return db.scalars(
            sa.select(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.id == key_id)
        ).first()


def _owner_with_keys(committed_sessions, sign_in, count: int = 2):
    with committed_sessions() as db:
        user = make_user(db)
        keys = [make_api_key(db, user, scopes=_SCOPES, name=f"key {index}")[0] for index in range(count)]
        db.commit()
    return sign_in(user), keys


class TestOwnKeys:
    def test_the_list_shows_the_keys_without_their_secrets(self, committed_sessions, sign_in):
        owner, keys = _owner_with_keys(committed_sessions, sign_in)

        body = owner.client.get(_API_KEYS).json()

        assert {item["id"] for item in body["items"]} == {str(key.id) for key in keys}
        assert all("key" not in item and "key_hash" not in item for item in body["items"])

    def test_a_key_is_created_once_with_its_secret_audited_and_announced(self, committed_sessions, sign_in):
        deliver_notices()
        owner, _ = _owner_with_keys(committed_sessions, sign_in, 0)

        response = owner.client.post(_API_KEYS, json={"name": "CLI", "scopes": ["account"], "step_up": _STEP_UP})

        assert response.status_code == 201
        assert response.headers["Cache-Control"] == "no-store"
        created = response.json()
        assert created["key"].startswith("endurain_")
        assert "key" not in owner.client.get(_API_KEYS).json()["items"][0]
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_CREATE)
        assert (row.target_id, row.target_owner_id, row.details) == (
            created["id"],
            str(owner.user.id),
            {"scopes": ["account"]},
        )
        assert created["key"] not in str(row.details)
        assert len(sent_to(owner.user.email)) == 1

    def test_an_account_at_the_key_limit_cannot_create_another(self, committed_sessions, sign_in):
        owner, _ = _owner_with_keys(committed_sessions, sign_in, api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER)

        response = owner.client.post(_API_KEYS, json={"name": "one more", "scopes": ["account"], "step_up": _STEP_UP})

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:api-key-limit"

    def test_a_wrong_password_creates_no_key(self, committed_sessions, sign_in):
        owner, _ = _owner_with_keys(committed_sessions, sign_in, 0)

        response = owner.client.post(
            _API_KEYS, json={"name": "CLI", "scopes": ["account"], "step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert owner.client.get(_API_KEYS).json()["items"] == []

    def test_a_revoked_key_stays_listed_inactive_and_is_audited(self, committed_sessions, sign_in):
        owner, (key, _) = _owner_with_keys(committed_sessions, sign_in)

        response = owner.client.post(f"{_API_KEYS}/{key.id}/revoke")

        assert response.status_code == 204
        assert _key_row(committed_sessions, key.id).is_active is False
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_REVOKE)
        assert row.target_id == str(key.id)

    def test_a_deleted_key_is_gone_and_audited(self, committed_sessions, sign_in):
        owner, (key, other) = _owner_with_keys(committed_sessions, sign_in)

        response = owner.client.delete(f"{_API_KEYS}/{key.id}")

        assert response.status_code == 204
        assert _key_row(committed_sessions, key.id) is None
        assert _key_row(committed_sessions, other.id) is not None
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_DELETE)
        assert row.target_id == str(key.id)

    def test_another_users_key_is_not_found_for_revoke_and_delete(self, committed_sessions, sign_in):
        owner, _ = _owner_with_keys(committed_sessions, sign_in)
        _, (foreign, _) = _owner_with_keys(committed_sessions, sign_in)

        assert owner.client.post(f"{_API_KEYS}/{foreign.id}/revoke").status_code == 404
        assert owner.client.delete(f"{_API_KEYS}/{foreign.id}").status_code == 404
        assert _key_row(committed_sessions, foreign.id).is_active is True


class _Managed:
    """An administrator, and a user with two active keys."""

    def __init__(self, committed_sessions, sign_in) -> None:
        with committed_sessions() as db:
            admin = make_admin(db)
            self.user = make_user(db)
            self.keys = [make_api_key(db, self.user, scopes=_SCOPES, name=f"key {i}")[0] for i in range(2)]
            db.commit()
        self.admin = sign_in(admin)
        self.committed_sessions = committed_sessions

    def active(self) -> int:
        return sum(_key_row(self.committed_sessions, key.id).is_active for key in self.keys)


class TestAdministratorList:
    def test_an_administrator_lists_a_users_keys(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        body = managed.admin.client.get(f"{_USERS}/{managed.user.id}/api-keys").json()

        assert {item["id"] for item in body["items"]} == {str(key.id) for key in managed.keys}

    def test_an_unknown_user_is_not_found(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        assert managed.admin.client.get(f"{_USERS}/{uuid.uuid4()}/api-keys").status_code == 404

    def test_a_malformed_user_id_is_refused(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        assert managed.admin.client.get(f"{_USERS}/not-a-uuid/api-keys").status_code == 422


class TestAdministratorRevokesOne:
    def test_the_key_is_revoked_audited_without_a_secret_and_the_owner_is_told(self, committed_sessions, sign_in):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in)
        key = managed.keys[0]

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/api-keys/{key.id}/revoke", json={"step_up": _STEP_UP}
        )

        assert response.status_code == 204
        assert managed.active() == 1
        assert _key_row(committed_sessions, key.id).is_active is False
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEY_REVOKE)
        assert (row.target_id, row.target_owner_id, row.details) == (str(key.id), str(managed.user.id), None)
        assert len(sent_to(managed.user.email)) == 1

    def test_a_key_of_another_user_is_not_found_and_nothing_is_sent(self, committed_sessions, sign_in):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in)
        _, (foreign, _) = _owner_with_keys(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/api-keys/{foreign.id}/revoke", json={"step_up": _STEP_UP}
        )

        assert response.status_code == 404
        assert _key_row(committed_sessions, foreign.id).is_active is True
        assert audit_rows(committed_sessions, account_security_audit_actions.API_KEY_REVOKE) == []
        assert sent_to(managed.user.email) == []

    def test_a_wrong_administrator_password_revokes_nothing(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/api-keys/{managed.keys[0].id}/revoke",
            json={"step_up": {"current_password": "wrong"}},
        )

        assert response.status_code == 403
        assert managed.active() == 2

    def test_a_body_without_step_up_is_refused(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/api-keys/{managed.keys[0].id}/revoke", json={}
        )

        assert response.status_code == 422


class TestAdministratorRevokesAll:
    def test_every_active_key_goes_with_the_count_audited_and_the_owner_told(self, committed_sessions, sign_in):
        deliver_notices()
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(f"{_USERS}/{managed.user.id}/api-keys/revoke", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert managed.active() == 0
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEYS_REVOKE)
        assert (row.target_id, row.details["api_keys_revoked"]) == (str(managed.user.id), 2)
        assert len(sent_to(managed.user.email)) == 1

    def test_a_user_without_active_keys_is_audited_but_not_told(self, committed_sessions, sign_in):
        deliver_notices()
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db)
            db.commit()

        response = sign_in(admin).client.post(f"{_USERS}/{user.id}/api-keys/revoke", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.API_KEYS_REVOKE)
        assert row.details["api_keys_revoked"] == 0
        assert sent_to(user.email) == []

    def test_an_unknown_user_is_not_found(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(f"{_USERS}/{uuid.uuid4()}/api-keys/revoke", json={"step_up": _STEP_UP})

        assert response.status_code == 404
        assert managed.active() == 2

    def test_a_wrong_administrator_password_revokes_nothing(self, committed_sessions, sign_in):
        managed = _Managed(committed_sessions, sign_in)

        response = managed.admin.client.post(
            f"{_USERS}/{managed.user.id}/api-keys/revoke", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert managed.active() == 2
