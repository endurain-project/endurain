"""The test application is the production one: real routes, authentication and scope checks on the test database."""

import sqlalchemy as sa
from jasil.audit.models import AuditLog
from tests._factories.users import make_admin, make_user

import core.config as core_config
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.sessions.models as sessions_models

_PROFILE = f"{core_config.ROOT_PATH}/profile"


def _committed_user(committed_sessions, make=make_user):
    with committed_sessions() as db:
        user = make(db)
        db.commit()
    return user


def test_an_anonymous_request_to_a_protected_route_gets_the_bearer_challenge(client):
    response = client.get(_PROFILE)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_a_signed_in_user_reads_their_own_profile(committed_sessions, sign_in):
    user = _committed_user(committed_sessions)

    response = sign_in(user).client.get(_PROFILE)

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


def test_a_token_whose_session_has_ended_is_refused(committed_sessions, sign_in):
    signed_in = sign_in(_committed_user(committed_sessions))
    with committed_sessions() as db:
        db.execute(
            sa.delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == signed_in.session_id)
        )
        db.commit()

    assert signed_in.client.get(_PROFILE).status_code == 401


def test_routes_live_under_the_api_root_only(committed_sessions, sign_in):
    client = sign_in(_committed_user(committed_sessions)).client

    assert client.get("/profile").status_code == 404


def test_a_regular_user_lacks_an_administrators_scope_and_the_refusal_is_audited(committed_sessions, sign_in):
    user = _committed_user(committed_sessions)

    response = sign_in(user).client.get(f"{core_config.ROOT_PATH}/users/{user.id}/identity-providers")

    assert response.status_code == 403
    assert response.json()["type"] == "urn:endurain:error:permission-denied"
    assert response.json()["missing_scopes"] == ["users:read-all"]
    assert 'error="insufficient_scope"' in response.headers["WWW-Authenticate"]
    with committed_sessions() as db:
        denied = db.scalars(
            sa.select(AuditLog).where(AuditLog.action_id == authentication_audit_actions.SCOPE_DENIED.id)
        )
        assert [(row.outcome, row.actor_id) for row in denied] == [("denied", str(user.id))]


def test_an_administrator_holds_it(committed_sessions, sign_in):
    admin = _committed_user(committed_sessions, make_admin)

    response = sign_in(admin).client.get(f"{core_config.ROOT_PATH}/users/{admin.id}/identity-providers")

    assert response.status_code == 200
