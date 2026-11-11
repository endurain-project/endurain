"""The "Require MFA" setting: who it covers, how a principal carries it and which requests it still lets through."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.authentication.principal_service as principal_service
import modules.auth.constants as auth_constants
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.contracts as server_settings_contracts
from modules.auth.access_tokens.contracts import TokenType
from modules.auth.contracts import AccessTokenCred, Principal

_MODULE = "modules.auth.authentication.principal_service"
_ENROLMENT_REQUIRED = "urn:endurain:error:mfa-enrolment-required"
_RequireMfa = server_settings_contracts.RequireMfa


def _policy(require_mfa: _RequireMfa) -> server_settings_contracts.AccessPolicy:
    return server_settings_contracts.AccessPolicy(
        session=server_settings_contracts.SessionPolicy(
            access_token_ttl=timedelta(minutes=15),
            refresh_token_ttl=timedelta(days=7),
            idle_timeout=None,
            absolute_timeout=timedelta(days=30),
            api_key_max_lifetime=timedelta(days=365),
        ),
        require_mfa=require_mfa,
    )


def _user(access_type: str):
    return SimpleNamespace(id=1, username="u", email="u@example.com", active=True, access_type=access_type)


def _token_manager():
    claims = {"sub": "1", "sid": "session-1", "scope": " ".join(auth_constants.ADMIN_ACCESS_SCOPE)}
    manager = MagicMock()

    def claim(_token, name, token_type):
        assert token_type is TokenType.ACCESS
        return claims[name]

    manager.get_token_claim.side_effect = claim
    return manager


def _session():
    now = datetime.now(UTC)
    return SimpleNamespace(user_id=1, last_activity_at=now, created_at=now)


def _resolve(access_type: str, require_mfa: _RequireMfa, *, enrolled: bool):
    with (
        patch(f"{_MODULE}.users_integration.get_user", return_value=_user(access_type)),
        patch(f"{_MODULE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_MODULE}.server_settings_integration.get_access_policy", return_value=_policy(require_mfa)),
        patch(
            f"{_MODULE}.mfa_integration.get_mfa_enabled_for_users", return_value={1: True} if enrolled else {}
        ) as mfa,
    ):
        principal = principal_service.resolve_from_access_token("token", _token_manager(), MagicMock())
    return principal, mfa


class TestPrincipalCarriesTheRequirement:
    @pytest.mark.parametrize(
        ("require_mfa", "access_type", "refused"),
        [
            (_RequireMfa.OFF, "admin", False),
            (_RequireMfa.OFF, "regular", False),
            (_RequireMfa.ADMINISTRATORS, "admin", True),
            (_RequireMfa.ADMINISTRATORS, "regular", False),
            (_RequireMfa.EVERYONE, "admin", True),
            (_RequireMfa.EVERYONE, "regular", True),
        ],
    )
    def test_a_covered_account_without_mfa_must_enrol(self, require_mfa, access_type, refused):
        principal, _ = _resolve(access_type, require_mfa, enrolled=False)

        assert principal.mfa_enrolment_required is refused

    @pytest.mark.parametrize("require_mfa", list(_RequireMfa))
    @pytest.mark.parametrize("access_type", ["admin", "regular"])
    def test_an_account_with_mfa_never_has_to_enrol(self, require_mfa, access_type):
        principal, _ = _resolve(access_type, require_mfa, enrolled=True)

        assert principal.mfa_enrolment_required is False

    def test_nothing_extra_is_read_while_the_setting_is_off(self):
        _, mfa = _resolve("admin", _RequireMfa.OFF, enrolled=False)

        mfa.assert_not_called()

    def test_nothing_extra_is_read_for_an_account_the_setting_does_not_cover(self):
        _, mfa = _resolve("regular", _RequireMfa.ADMINISTRATORS, enrolled=False)

        mfa.assert_not_called()

    def test_a_covered_account_costs_one_indexed_lookup(self):
        _, mfa = _resolve("admin", _RequireMfa.ADMINISTRATORS, enrolled=False)

        mfa.assert_called_once()
        assert mfa.call_args.args[0] == [1]


def _principal(*, enrolment_required: bool) -> Principal:
    return Principal(
        user_id=1,
        username="u",
        email="u@example.com",
        is_active=True,
        is_superuser=True,
        scopes=frozenset(auth_constants.ADMIN_ACCESS_SCOPE),
        credential=AccessTokenCred(session_id="s"),
        mfa_enrolment_required=enrolment_required,
    )


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    root = core_config.ROOT_PATH

    def _ok():
        return {}

    protected = [Depends(auth_dependencies.authenticate)]
    scoped = [Depends(auth_dependencies.check_scopes)]
    for method, path in auth_constants.MFA_ENROLMENT_ROUTES:
        app.add_api_route(root + path, _ok, methods=[method], dependencies=protected)
    app.add_api_route(root + "/profile/mfa/disable", _ok, methods=["POST"], dependencies=scoped)
    app.add_api_route(root + "/profile/mfa/status", _ok, methods=["POST"], dependencies=protected)
    app.add_api_route(root + "/profile/password/change", _ok, methods=["POST"], dependencies=protected)
    app.add_api_route(root + "/server_settings", _ok, methods=["GET"], dependencies=protected)
    return TestClient(app, headers={"Authorization": "Bearer token"})


def _resolving(principal: Principal):
    return patch.object(
        auth_dependencies.authentication_integration, "resolve_from_access_token", return_value=principal
    )


class TestTheRefusal:
    def test_a_covered_account_without_mfa_is_refused_with_its_own_problem_type(self, client):
        with _resolving(_principal(enrolment_required=True)):
            response = client.post(core_config.ROOT_PATH + "/profile/password/change")

        assert response.status_code == 403
        assert response.json()["type"] == _ENROLMENT_REQUIRED

    def test_the_refusal_is_not_an_insufficient_scope_challenge(self, client):
        with _resolving(_principal(enrolment_required=True)):
            response = client.post(core_config.ROOT_PATH + "/profile/password/change")

        assert "www-authenticate" not in response.headers

    def test_a_scope_checked_route_is_refused_the_same_way(self, client):
        with _resolving(_principal(enrolment_required=True)):
            response = client.post(core_config.ROOT_PATH + "/profile/mfa/disable")

        assert response.status_code == 403
        assert response.json()["type"] == _ENROLMENT_REQUIRED

    def test_an_api_key_of_such_an_account_is_refused_too(self, client):
        with patch.object(
            auth_dependencies.authentication_integration,
            "resolve_from_api_key",
            return_value=_principal(enrolment_required=True),
        ):
            response = TestClient(client.app).get(
                core_config.ROOT_PATH + "/server_settings", headers={"X-API-Key": "k"}
            )

        assert response.status_code == 403
        assert response.json()["type"] == _ENROLMENT_REQUIRED

    def test_an_account_that_need_not_enrol_is_served(self, client):
        with _resolving(_principal(enrolment_required=False)):
            response = client.post(core_config.ROOT_PATH + "/profile/password/change")

        assert response.status_code == 200


class TestWhatAnUnenrolledAccountMayStillDo:
    @pytest.mark.parametrize(("method", "path"), sorted(auth_constants.MFA_ENROLMENT_ROUTES))
    def test_each_route_it_needs_to_enrol_is_served(self, client, method, path):
        with _resolving(_principal(enrolment_required=True)):
            response = client.request(method, core_config.ROOT_PATH + path.replace("{idp_id}", "3"))

        assert response.status_code == 200

    def test_the_exemption_is_the_method_and_the_route_not_the_path_alone(self, client):
        """``POST /profile/mfa/status`` is not ``GET``: the exemption names the method."""
        with _resolving(_principal(enrolment_required=True)):
            response = client.post(core_config.ROOT_PATH + "/profile/mfa/status")

        assert response.status_code == 403

    def test_the_exempt_set_is_exactly_what_the_enrolment_page_needs(self):
        needed = {
            ("GET", "/profile"),
            ("GET", "/profile/mfa/status"),
            ("POST", "/profile/mfa/setup"),
            ("POST", "/profile/mfa/enable"),
            ("GET", "/profile/identity-providers"),
            ("POST", "/profile/identity-providers/{idp_id}/step-up"),
        }

        assert set(auth_constants.MFA_ENROLMENT_ROUTES) == needed
