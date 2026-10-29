"""Starting an identity-provider step-up: the service's order of work and the route's cookie."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.account_security.identity_links_router as identity_links_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.utils as idp_utils
from modules.auth.identity_providers.constants import StepUpAction

SESSION_ID = "11111111-2222-3333-4444-555555555555"
START = idp_schema.StepUpStartRequest(
    code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    action=StepUpAction.MFA_DISABLE,
    redirect="/settings/security",
)


def _staged() -> SimpleNamespace:
    return SimpleNamespace(browser_binding="binding-secret")


class TestStartService:
    def _start(self, *, has_password=False, db=None):
        db = db or MagicMock()
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        with (
            patch.object(identity_link_service.step_up_service, "require_not_locked_out") as locked,
            patch.object(
                identity_link_service.credentials_integration, "has_local_password", return_value=has_password
            ),
            patch.object(
                identity_link_service.identity_providers_integration, "stage_step_up", return_value=_staged()
            ) as stage,
            patch.object(
                identity_link_service.identity_providers_integration,
                "authorization_url",
                return_value="https://idp.example.com/authorize?prompt=login",
            ) as url,
        ):
            order.attach_mock(url, "authorization_url")
            flow = identity_link_service.start_idp_step_up(3, START, "1.2.3.4", 7, SESSION_ID, MagicMock(), db)
        return flow, stage, order, locked

    def test_the_state_is_committed_before_the_provider_url_is_built(self):
        flow, stage, order, _ = self._start()

        assert [call[0] for call in order.mock_calls] == ["commit", "authorization_url"]
        assert stage.call_args.args[:7] == (
            7,
            SESSION_ID,
            3,
            StepUpAction.MFA_DISABLE,
            START.code_challenge,
            "/settings/security",
            "1.2.3.4",
        )
        assert flow == idp_contracts.BrowserFlowStart(
            authorization_url="https://idp.example.com/authorize?prompt=login", browser_binding="binding-secret"
        )

    def test_an_account_with_a_password_steps_up_with_it_instead(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            self._start(has_password=True)

    def test_a_locked_out_user_is_refused_before_anything_is_staged(self):
        with (
            patch.object(
                identity_link_service.step_up_service,
                "require_not_locked_out",
                side_effect=core_exceptions.TooManyRequestsError("locked"),
            ),
            patch.object(identity_link_service.identity_providers_integration, "stage_step_up") as stage,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            identity_link_service.start_idp_step_up(3, START, "1.2.3.4", 7, SESSION_ID, MagicMock(), MagicMock())

        stage.assert_not_called()


class TestStartRoute:
    @pytest.fixture
    def client(self):
        app = FastAPI()
        app.include_router(identity_links_router.router, prefix=core_config.ROOT_PATH + "/profile/identity-providers")
        core_exceptions.register_exception_handlers(app)
        app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
        app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
        app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: SESSION_ID
        app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
        app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: MagicMock()
        return TestClient(app)

    def test_the_route_returns_the_url_and_binds_the_browser(self, client):
        flow = idp_contracts.BrowserFlowStart(
            authorization_url="https://idp.example.com/authorize", browser_binding="binding-secret"
        )
        with patch.object(identity_link_service, "start_idp_step_up", return_value=flow) as start:
            response = client.post(
                core_config.ROOT_PATH + "/profile/identity-providers/3/step-up", json=START.model_dump(mode="json")
            )

        assert response.status_code == 200
        assert response.json() == {"authorization_url": "https://idp.example.com/authorize"}
        assert response.cookies.get(idp_dependencies.BINDING_COOKIE_NAME) == "binding-secret"
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert f"path={idp_dependencies.BINDING_COOKIE_PATH}".lower() in cookie
        assert start.call_args.args[3:5] == (7, SESSION_ID)

    @pytest.mark.parametrize(
        "body",
        [
            {"code_challenge": "short", "action": "mfa_disable", "redirect": "/"},
            {"code_challenge": "c" * 43, "action": "password_change", "redirect": "/"},
            {"code_challenge": "c" * 43, "action": "mfa_disable"},
            {"code_challenge": "c" * 43, "action": "mfa_disable", "redirect": "/", "extra": 1},
        ],
        ids=["short-challenge", "unknown-action", "no-redirect", "unknown-field"],
    )
    def test_a_malformed_request_is_refused(self, client, body):
        with patch.object(identity_link_service, "start_idp_step_up") as start:
            response = client.post(core_config.ROOT_PATH + "/profile/identity-providers/3/step-up", json=body)

        assert response.status_code == 422
        start.assert_not_called()


class TestResultUrl:
    def test_the_outcome_travels_in_the_fragment(self):
        url = idp_utils.build_step_up_result_url(
            "https://app.example.com", "/settings/security?tab=1", {"step_up_ticket": "t-1"}
        )

        assert url == "https://app.example.com/settings/security?tab=1#step_up_ticket=t-1"

    def test_without_a_return_path_it_goes_to_the_security_settings(self):
        url = idp_utils.build_step_up_result_url("https://app.example.com", None, {"step_up_error": "failed"})

        assert url == "https://app.example.com/settings/security#step_up_error=failed"
