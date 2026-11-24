"""How a request is authenticated, scoped and audited: the dependencies every route reaches its caller through."""

import pytest
from fastapi.testclient import TestClient

import core.config as core_config
import core.exceptions as core_exceptions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.sessions.audit_actions as sessions_audit_actions
from tests._factories.account_security import make_oidc_provider, session_ids, step_up_proof
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.identity_links import make_identity_link
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_admin, make_user

_PROFILE = f"{core_config.ROOT_PATH}/profile"
_TICKET = f"{core_config.ROOT_PATH}/ws/ticket"
_ACCOUNT = [api_keys_constants.ApiKeyScope.ACCOUNT]
_INVALID_TOKEN = "urn:endurain:error:invalid-token"


def _holder(app, committed_sessions, *, scopes=_ACCOUNT, user=None):
    with committed_sessions() as db:
        owner = user or make_user(db)
        key, raw_key = make_api_key(db, owner, scopes=scopes)
        db.commit()
    return key_client(app, owner, key, raw_key)


class TestResolvingTheCaller:
    def test_a_request_without_credentials_is_refused_with_a_bare_bearer_challenge(self, client):
        response = client.get(_PROFILE)

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_a_malformed_bearer_token_is_an_invalid_token(self, client):
        response = client.get(_PROFILE, headers={"Authorization": "Bearer not-a-token"})

        assert response.status_code == 401
        assert response.json()["type"] == _INVALID_TOKEN

    def test_an_api_key_in_the_header_is_served_as_its_owner(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)

        response = holder.client.get(_PROFILE)

        assert response.status_code == 200
        assert response.json()["id"] == str(holder.user.id)

    def test_a_bearer_token_wins_over_an_api_key(self, app, committed_sessions, sign_in):
        holder = _holder(app, committed_sessions)
        with committed_sessions() as db:
            other = make_user(db)
            db.commit()
        signed_in = sign_in(other)

        response = TestClient(app).get(
            _PROFILE,
            headers={
                "Authorization": f"Bearer {signed_in.access_token}",
                "X-Client-Type": "web",
                "X-API-Key": holder.raw_key,
            },
        )

        assert response.json()["id"] == str(other.id)

    def test_the_api_key_in_the_query_string_is_ignored_by_default(self, app, committed_sessions):
        holder = _holder(app, committed_sessions)

        response = TestClient(app).get(_PROFILE, params={"api_key": holder.raw_key})

        assert response.status_code == 401

    def test_the_api_key_in_the_query_string_is_accepted_when_the_server_allows_it(
        self, app, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "ALLOW_API_KEY_QUERY_PARAM", True)
        holder = _holder(app, committed_sessions)

        response = TestClient(app).get(_PROFILE, params={"api_key": holder.raw_key})

        assert response.status_code == 200
        assert response.json()["id"] == str(holder.user.id)

    def test_the_header_wins_over_the_query_string_key(self, app, committed_sessions, monkeypatch):
        monkeypatch.setattr(core_config.settings, "ALLOW_API_KEY_QUERY_PARAM", True)
        holder = _holder(app, committed_sessions)

        response = TestClient(app, headers={"X-API-Key": holder.raw_key}).get(_PROFILE, params={"api_key": "wrong"})

        assert response.status_code == 200


class TestScopes:
    def test_a_key_without_the_routes_scope_is_refused_naming_it_and_the_refusal_is_audited_against_the_key(
        self, app, committed_sessions
    ):
        holder = _holder(app, committed_sessions, scopes=[api_keys_constants.ApiKeyScope.HEALTH_READ])

        response = holder.client.get(f"{core_config.ROOT_PATH}/gears")

        assert response.status_code == 403
        assert response.headers["WWW-Authenticate"] == 'Bearer error="insufficient_scope", scope="gears:read"'
        assert response.json()["missing_scopes"] == ["gears:read"]
        (row,) = audit_rows(committed_sessions, authentication_audit_actions.SCOPE_DENIED)
        assert (row.outcome, row.actor_type, row.actor_id, row.credential_type, row.credential_id) == (
            "denied",
            "api_key",
            str(holder.user.id),
            "api_key",
            str(holder.key.id),
        )
        assert row.details == {"missing_scopes": ["gears:read"]}

    def test_a_key_holding_the_scope_is_served_and_nothing_is_audited(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, scopes=[api_keys_constants.ApiKeyScope.GEARS_READ])

        assert holder.client.get(f"{core_config.ROOT_PATH}/gears").status_code == 200
        assert audit_rows(committed_sessions, authentication_audit_actions.SCOPE_DENIED) == []

    def test_a_scope_a_route_needs_on_some_inputs_gets_the_same_refusal(self):
        with pytest.raises(core_exceptions.PermissionDeniedError) as refused:
            auth_dependencies.require_scopes({"users:read"}, "users:read", "users:write")

        assert refused.value.status_code == 403
        assert refused.value.extensions == {"missing_scopes": ["users:write"]}


class TestSessionOnlyRoutes:
    def test_a_key_is_refused_where_a_signed_in_session_is_needed(self, app, committed_sessions):
        holder = _holder(app, committed_sessions, scopes=[api_keys_constants.ApiKeyScope.NOTIFICATIONS_READ])

        response = holder.client.post(_TICKET)

        assert response.status_code == 403
        assert "signed-in session" in response.json()["detail"]

    def test_a_session_gets_what_the_route_issues(self, sign_in, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()

        assert sign_in(user).client.post(_TICKET).status_code == 201


class TestAuditContext:
    def test_a_row_written_in_a_request_names_the_user_the_credential_and_the_client(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        here, there = sign_in(user), sign_in(user)

        here.client.delete(f"{_PROFILE}/sessions/{there.session_id}", headers={"User-Agent": "pytest-agent/1.0"})

        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.actor_type, row.actor_id, row.credential_type, row.user_agent, row.source) == (
            "user",
            str(user.id),
            "access_token",
            "pytest-agent/1.0",
            "api",
        )
        assert row.credential_id is not None and row.credential_id != row.actor_id

    def test_outside_a_request_the_system_acts(self):
        context = auth_dependencies.audit_context_from_request()

        assert context.actor_type.value == "system"
        assert context.source.value == "worker"


class TestAdministratorStepUpVerifier:
    def _users_and_sessions(self, committed_sessions):
        with committed_sessions() as db:
            admin = make_admin(db)
            user = make_user(db)
            db.commit()
        return admin, user

    def test_the_administrators_own_password_authorises_ending_a_users_sessions(self, committed_sessions, sign_in):
        admin, user = self._users_and_sessions(committed_sessions)
        victim = sign_in(user)

        response = sign_in(admin).client.post(
            f"{core_config.ROOT_PATH}/users/{user.id}/sessions/revoke", json={"step_up": {"current_password": PASSWORD}}
        )

        assert response.status_code == 204
        assert session_ids(committed_sessions, user.id) == set()
        assert victim.client.get(_PROFILE).status_code == 401

    def test_a_wrong_password_ends_nothing(self, committed_sessions, sign_in):
        admin, user = self._users_and_sessions(committed_sessions)
        sign_in(user)

        response = sign_in(admin).client.post(
            f"{core_config.ROOT_PATH}/users/{user.id}/sessions/revoke", json={"step_up": {"current_password": "wrong"}}
        )

        assert response.status_code == 403
        assert len(session_ids(committed_sessions, user.id)) == 1

    def test_a_ticket_issued_for_another_operation_does_not_authorise_it(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            admin = make_admin(db, with_password=False)
            idp_id = make_oidc_provider(db, "admin-idp")
            make_identity_link(db, admin.id, idp_id, "subject")
            user = make_user(db)
            db.commit()
        signed_in = sign_in(admin)
        sign_in(user)
        with committed_sessions() as db:
            wrong = step_up_proof(
                db,
                admin,
                signed_in.session_id,
                idp_id,
                action=identity_providers_constants.StepUpAction.ADMIN_USER_EDIT,
            )
            right = step_up_proof(
                db,
                admin,
                signed_in.session_id,
                idp_id,
                action=identity_providers_constants.StepUpAction.ADMIN_SESSIONS_REVOKE,
            )
        url = f"{core_config.ROOT_PATH}/users/{user.id}/sessions/revoke"

        refused = signed_in.client.post(url, json={"step_up": {"idp_reauth": wrong}})
        accepted = signed_in.client.post(url, json={"step_up": {"idp_reauth": right}})

        assert (refused.status_code, accepted.status_code) == (403, 204)
        assert session_ids(committed_sessions, user.id) == set()
