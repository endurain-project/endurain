"""An access token is honoured only while its session exists, with the rights its scope and the user's role share.

Tokens are signed with the application's own key; the claims they carry are what each test varies.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from joserfc import jwt

import core.config as core_config
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_admin, make_user

_PROFILE = f"{core_config.ROOT_PATH}/profile"
_GEARS = f"{core_config.ROOT_PATH}/gears"
_USERS = f"{core_config.ROOT_PATH}/users"
_ACCESS = access_tokens_service.TokenType.ACCESS
_INVALID_TOKEN = "urn:endurain:error:invalid-token"


def _forge(signed_in, **claims: object) -> TestClient:
    """Return a client that sends the signed-in user's access token with some of its claims replaced.

    The token is signed with the application's key, so only the claims differ from a genuine one.
    """
    manager = access_tokens_integration.get_token_manager()
    genuine = dict(manager.decode_token(signed_in.access_token, _ACCESS).claims)
    genuine.update(claims)
    header = {"alg": manager.algorithm, "typ": _ACCESS.header_type, "kid": manager._signing_keys[_ACCESS].kid}
    token = jwt.encode(header, genuine, manager._signing_keys[_ACCESS])
    return TestClient(signed_in.client.app, headers={"Authorization": f"Bearer {token}", "X-Client-Type": "web"})


def _age_session(committed_sessions, session_id: uuid.UUID, *, idle_for=timedelta(0), age=timedelta(0)) -> None:
    now = datetime.now(UTC)
    with committed_sessions() as db:
        db.execute(
            sa.update(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.id == session_id)
            .values(last_activity_at=now - idle_for, created_at=now - age)
        )
        db.commit()


def _signed_in(committed_sessions, sign_in, *, admin: bool = False):
    with committed_sessions() as db:
        user = make_admin(db) if admin else make_user(db)
        db.commit()
    return sign_in(user)


class TestClaims:
    def test_a_token_of_a_live_session_is_accepted_as_its_user(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)

        response = signed_in.client.get(_PROFILE)

        assert response.status_code == 200
        assert response.json()["id"] == str(signed_in.user.id)

    @pytest.mark.parametrize("sub", ["1", "123456", "not-a-user-id", "", "../1", 7, None])
    def test_a_sub_that_is_not_a_user_id_is_refused(self, committed_sessions, sign_in, sub):
        signed_in = _signed_in(committed_sessions, sign_in)

        response = _forge(signed_in, sub=sub).get(_PROFILE)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN

    @pytest.mark.parametrize("sid", ["session-1", "", "../1", 7, None])
    def test_a_sid_that_is_not_a_session_id_is_refused(self, committed_sessions, sign_in, sid):
        signed_in = _signed_in(committed_sessions, sign_in)

        assert _forge(signed_in, sid=sid).get(_PROFILE).status_code == 401

    def test_a_token_of_an_unknown_user_is_an_invalid_token(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)

        response = _forge(signed_in, sub=str(uuid.uuid4())).get(_PROFILE)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN

    def test_a_token_of_a_deactivated_user_is_an_invalid_token(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        with committed_sessions() as db:
            db.execute(sa.text("UPDATE users SET active = false WHERE id = :id"), {"id": signed_in.user.id})
            db.commit()

        response = signed_in.client.get(_PROFILE)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN

    def test_a_token_whose_session_was_revoked_is_refused(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        other = sign_in(signed_in.user)
        assert other.client.delete(f"{_PROFILE}/sessions/{signed_in.session_id}").status_code == 204

        assert signed_in.client.get(_PROFILE).status_code == 401

    def test_a_token_naming_another_users_session_is_refused(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        stranger = _signed_in(committed_sessions, sign_in)

        assert _forge(signed_in, sid=str(stranger.session_id)).get(_PROFILE).status_code == 401


class TestScopes:
    def test_a_demoted_admin_loses_the_admin_scopes_of_a_token_issued_before(self, committed_sessions, sign_in):
        admin = _signed_in(committed_sessions, sign_in, admin=True)
        with committed_sessions() as db:
            target = make_user(db)
            db.commit()
        assert admin.client.get(f"{_USERS}/{target.id}/identity-providers").status_code == 200
        with committed_sessions() as db:
            db.execute(
                sa.text("UPDATE users SET access_type = :regular WHERE id = :id"),
                {"regular": users_schema.UserAccessType.REGULAR.value, "id": admin.user.id},
            )
            db.commit()

        response = admin.client.get(f"{_USERS}/{target.id}/identity-providers")

        assert response.status_code == 403
        assert response.json()["missing_scopes"]

    def test_a_token_narrower_than_the_role_holds_only_its_own_scopes(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in, admin=True)
        narrow = _forge(signed_in, scope="gears:read")

        assert narrow.get(_GEARS).status_code == 200
        assert narrow.get(_PROFILE).status_code == 403

    def test_a_token_cannot_claim_a_scope_its_users_role_lacks(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in)
        with committed_sessions() as db:
            target = make_user(db)
            db.commit()
        greedy = _forge(signed_in, scope="gears:read users:read-all")

        assert greedy.get(_GEARS).status_code == 200
        assert greedy.get(f"{_USERS}/{target.id}/identity-providers").status_code == 403

    def test_a_token_scope_the_server_never_mints_grants_nothing(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in, admin=True)
        odd = _forge(signed_in, scope="gears:read root")

        assert odd.get(_GEARS).status_code == 200
        assert odd.get(_PROFILE).status_code == 403

    def test_a_token_without_scopes_holds_none(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in, admin=True)

        assert _forge(signed_in, scope=" ").get(_GEARS).status_code == 403

    def test_a_scope_claim_that_is_not_a_string_is_refused(self, committed_sessions, sign_in):
        signed_in = _signed_in(committed_sessions, sign_in, admin=True)

        response = _forge(signed_in, scope=["gears:read"]).get(_GEARS)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN


class TestSessionLifetime:
    def _policy(self, committed_sessions, **fields) -> None:
        with committed_sessions() as db:
            edit_server_settings(db, **fields)
            db.commit()

    def test_a_session_idle_beyond_the_policy_is_an_invalid_token(self, committed_sessions, sign_in):
        self._policy(committed_sessions, session_idle_timeout_enabled=True, session_idle_timeout_hours=1)
        signed_in = _signed_in(committed_sessions, sign_in)
        _age_session(committed_sessions, signed_in.session_id, idle_for=timedelta(hours=2))

        response = signed_in.client.get(_PROFILE)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN

    def test_a_session_inside_the_idle_window_is_accepted(self, committed_sessions, sign_in):
        self._policy(committed_sessions, session_idle_timeout_enabled=True, session_idle_timeout_hours=1)
        signed_in = _signed_in(committed_sessions, sign_in)
        _age_session(committed_sessions, signed_in.session_id, idle_for=timedelta(minutes=30))

        assert signed_in.client.get(_PROFILE).status_code == 200

    def test_inactivity_is_ignored_while_the_idle_timeout_is_off(self, committed_sessions, sign_in):
        self._policy(committed_sessions, session_idle_timeout_enabled=False)
        signed_in = _signed_in(committed_sessions, sign_in)
        _age_session(committed_sessions, signed_in.session_id, idle_for=timedelta(days=3))

        assert signed_in.client.get(_PROFILE).status_code == 200

    def test_a_session_older_than_the_absolute_timeout_is_an_invalid_token(self, committed_sessions, sign_in):
        self._policy(committed_sessions, session_absolute_timeout_hours=24 * 30)
        signed_in = _signed_in(committed_sessions, sign_in)
        _age_session(committed_sessions, signed_in.session_id, age=timedelta(days=40))

        assert signed_in.client.get(_PROFILE).status_code == 401

    def test_a_shortened_policy_applies_to_a_session_that_was_valid_before(self, committed_sessions, sign_in):
        self._policy(committed_sessions, session_idle_timeout_enabled=True, session_idle_timeout_hours=2)
        signed_in = _signed_in(committed_sessions, sign_in)
        _age_session(committed_sessions, signed_in.session_id, idle_for=timedelta(minutes=90))
        assert signed_in.client.get(_PROFILE).status_code == 200

        self._policy(committed_sessions, session_idle_timeout_hours=1)

        assert signed_in.client.get(_PROFILE).status_code == 401
