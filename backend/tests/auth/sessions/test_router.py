"""The administrator's session routes: listing a user's sessions and ending one or all of them behind a step-up."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.auth.sessions.models as sessions_models
from tests._factories.auth import make_session
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_admin, make_user

_USERS = f"{core_config.ROOT_PATH}/users"
_SESSION_ID = uuid.UUID(int=0x5E55)
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_ITEM_FIELDS = {
    "id",
    "user_id",
    "ip_address",
    "device_type",
    "operating_system",
    "operating_system_version",
    "browser",
    "browser_version",
    "created_at",
    "last_activity_at",
    "expires_at",
    "is_current",
    "app_redirect_uri",
}


def _admin_and_user(committed_sessions, sign_in, *, sessions: int = 0):
    with committed_sessions() as db:
        admin, user = make_admin(db), make_user(db)
        made = [make_session(db, user) for _ in range(sessions)]
        db.commit()
    return sign_in(admin), user, made


def _remaining(committed_sessions, user_id) -> set[uuid.UUID]:
    with committed_sessions() as db:
        return set(
            db.scalars(
                sa.select(sessions_models.UsersSessions.id).where(sessions_models.UsersSessions.user_id == user_id)
            )
        )


class TestListSessions:
    def test_an_administrator_reads_a_page_of_the_exchanged_sessions_of_a_user(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=3)
        with committed_sessions() as db:
            make_session(db, user, exchanged=False)
            db.commit()

        response = me.client.get(f"{_USERS}/{user.id}/sessions", params={"page_number": 2, "num_records": 1})

        body = response.json()
        assert response.status_code == 200
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (3, 2, 1, 3)
        assert len(body["items"]) == 1
        assert set(body["items"][0]) == _ITEM_FIELDS
        assert uuid.UUID(body["items"][0]["id"]) in {s.id for s in made}
        assert body["items"][0]["is_current"] is False

    def test_the_default_window_holds_every_session_of_a_small_set_newest_first(self, committed_sessions, sign_in):
        me, user, _ = _admin_and_user(committed_sessions, sign_in)
        now = datetime.now(UTC)
        with committed_sessions() as db:
            old = make_session(db, user, created_at=now - timedelta(hours=2))
            new = make_session(db, user, created_at=now - timedelta(hours=1))
            db.commit()

        body = me.client.get(f"{_USERS}/{user.id}/sessions").json()

        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert body["num_records"] == 25

    def test_a_user_with_no_sessions_has_an_empty_page(self, committed_sessions, sign_in):
        me, user, _ = _admin_and_user(committed_sessions, sign_in)

        body = me.client.get(f"{_USERS}/{user.id}/sessions").json()

        assert (body["items"], body["total"]) == ([], 0)

    def test_the_callers_own_session_is_marked_current(self, committed_sessions, sign_in):
        me, _, _ = _admin_and_user(committed_sessions, sign_in)

        items = me.client.get(f"{_USERS}/{me.user.id}/sessions").json()["items"]

        assert {item["id"]: item["is_current"] for item in items} == {str(me.session_id): True}

    def test_a_page_size_above_the_cap_is_422(self, committed_sessions, sign_in):
        me, user, _ = _admin_and_user(committed_sessions, sign_in)

        assert me.client.get(f"{_USERS}/{user.id}/sessions", params={"num_records": 201}).status_code == 422

    def test_the_demo_environment_lists_nothing(self, monkeypatch, committed_sessions, sign_in):
        me, user, _ = _admin_and_user(committed_sessions, sign_in, sessions=2)
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        body = me.client.get(f"{_USERS}/{user.id}/sessions").json()

        assert (body["items"], body["total"]) == ([], 0)

    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("get", "/{}/sessions", {}),
            ("post", f"/{{}}/sessions/{_SESSION_ID}/revoke", {"json": _STEP_UP}),
            ("post", "/{}/sessions/revoke", {"json": _STEP_UP}),
        ],
    )
    @pytest.mark.parametrize("malformed", ["0", "7", "not-a-uuid"])
    def test_a_malformed_user_id_is_422_on_every_session_route(
        self, committed_sessions, sign_in, method, path, kwargs, malformed
    ):
        me, _, _ = _admin_and_user(committed_sessions, sign_in)

        response = getattr(me.client, method)(_USERS + path.format(malformed), **kwargs)

        assert response.status_code == 422


class TestRevokeOne:
    def test_an_administrator_ends_a_session_behind_a_step_up_and_it_is_audited(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=2)

        response = me.client.post(f"{_USERS}/{user.id}/sessions/{made[0].id}/revoke", json=_STEP_UP)

        assert response.status_code == 204
        assert _remaining(committed_sessions, user.id) == {made[1].id}
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_type, row.target_id, row.target_owner_id) == ("session", str(made[0].id), str(user.id))
        assert (row.actor_id, row.details) == (str(me.user.id), {"sessions_revoked": 1})

    def test_a_wrong_password_in_the_step_up_is_403_and_ends_nothing(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        response = me.client.post(
            f"{_USERS}/{user.id}/sessions/{made[0].id}/revoke", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert _remaining(committed_sessions, user.id) == {made[0].id}

    def test_a_request_without_a_step_up_is_422_and_ends_nothing(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        response = me.client.post(f"{_USERS}/{user.id}/sessions/{made[0].id}/revoke", json={})

        assert response.status_code == 422
        assert _remaining(committed_sessions, user.id) == {made[0].id}

    def test_a_session_the_user_does_not_have_is_404(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)
        with committed_sessions() as db:
            other = make_session(db, make_user(db))
            db.commit()

        missing = me.client.post(f"{_USERS}/{user.id}/sessions/{uuid.uuid4()}/revoke", json=_STEP_UP)
        theirs = me.client.post(f"{_USERS}/{user.id}/sessions/{other.id}/revoke", json=_STEP_UP)

        assert (missing.status_code, theirs.status_code) == (404, 404)
        assert _remaining(committed_sessions, user.id) == {made[0].id}
        assert _remaining(committed_sessions, other.user_id) == {other.id}
        assert audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE) == []

    def test_a_malformed_session_id_is_422(self, committed_sessions, sign_in):
        me, user, _ = _admin_and_user(committed_sessions, sign_in)

        assert me.client.post(f"{_USERS}/{user.id}/sessions/7/revoke", json=_STEP_UP).status_code == 422

    def test_the_delete_route_is_gone(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        response = me.client.delete(f"{_USERS}/{user.id}/sessions/{made[0].id}")

        assert response.status_code in (404, 405)
        assert _remaining(committed_sessions, user.id) == {made[0].id}


class TestRevokeAll:
    def test_it_ends_every_session_bumps_the_security_generation_and_audits_the_count(
        self, committed_sessions, sign_in
    ):
        me, user, _ = _admin_and_user(committed_sessions, sign_in, sessions=3)
        with committed_sessions() as db:
            before = security_generation_integration.current_generation(user.id, db)

        response = me.client.post(f"{_USERS}/{user.id}/sessions/revoke", json=_STEP_UP)

        assert response.status_code == 204
        assert _remaining(committed_sessions, user.id) == set()
        with committed_sessions() as db:
            assert security_generation_integration.current_generation(user.id, db) == before + 1
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_type, row.target_id, row.details) == ("user", str(user.id), {"sessions_revoked": 3})

    def test_the_excluded_session_stays_and_the_generation_does_not_move(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=3)
        with committed_sessions() as db:
            before = security_generation_integration.current_generation(user.id, db)

        response = me.client.post(
            f"{_USERS}/{user.id}/sessions/revoke", json=_STEP_UP, params={"exclude_session_id": str(made[1].id)}
        )

        assert response.status_code == 204
        assert _remaining(committed_sessions, user.id) == {made[1].id}
        with committed_sessions() as db:
            assert security_generation_integration.current_generation(user.id, db) == before

    def test_a_malformed_excluded_session_id_is_422(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        response = me.client.post(
            f"{_USERS}/{user.id}/sessions/revoke", json=_STEP_UP, params={"exclude_session_id": "7"}
        )

        assert response.status_code == 422
        assert _remaining(committed_sessions, user.id) == {made[0].id}

    def test_a_wrong_password_in_the_step_up_is_403_and_ends_nothing(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=2)

        response = me.client.post(
            f"{_USERS}/{user.id}/sessions/revoke", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"
        assert _remaining(committed_sessions, user.id) == {s.id for s in made}

    def test_a_request_without_a_step_up_is_422(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        assert me.client.post(f"{_USERS}/{user.id}/sessions/revoke", json={}).status_code == 422
        assert _remaining(committed_sessions, user.id) == {made[0].id}

    def test_the_delete_route_is_gone(self, committed_sessions, sign_in):
        me, user, made = _admin_and_user(committed_sessions, sign_in, sessions=1)

        assert me.client.delete(f"{_USERS}/{user.id}/sessions").status_code in (404, 405)
        assert _remaining(committed_sessions, user.id) == {made[0].id}
