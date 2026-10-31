"""Starting a step-up: the staged OAuth state and the authorization URL that asks for a fresh sign-in."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.oauth_state.constants as oauth_state_constants
from modules.auth.identity_providers.constants import STEP_UP_MAX_AGE_SECONDS, StepUpAction

HOST = "https://app.example.com"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _idp(**overrides):
    values = {
        "id": 3,
        "slug": "idp",
        "name": "Pocket ID",
        "enabled": True,
        "issuer_url": "https://idp.example.com",
        "authorization_endpoint": "https://idp.example.com/authorize",
        "scopes": None,
    }
    values.update(overrides)
    return idp_contracts.IdentityProviderState.model_construct(**values)


@pytest.fixture
def service():
    oidc = MagicMock()
    oidc.decrypt_client_id.return_value = "client-id"
    return authorization_service.AuthorizationService(oidc, HOST)


def _stage(service, *, idp=None, linked=True, redirect="/settings/security", challenge=CHALLENGE):
    with (
        patch.object(authorization_service.idp_crud, "get_identity_provider", return_value=idp or _idp()),
        patch.object(
            authorization_service.identity_provider_links_integration,
            "get_user_identity_provider_by_user_id_and_idp_id",
            return_value=SimpleNamespace() if linked else None,
        ),
        patch.object(authorization_service.oauth_state_integration, "create_oauth_state") as create,
    ):
        staged = service.stage_step_up(
            7, SESSION_ID, 3, StepUpAction.ACCOUNT_DELETE, challenge, redirect, "1.2.3.4", MagicMock()
        )
    return staged, create


class TestStageStepUp:
    def test_the_state_records_the_flow_session_action_and_binding(self, service):
        staged, create = _stage(service)

        kwargs = create.call_args.kwargs
        assert kwargs["purpose"] == oauth_state_constants.OAuthStatePurpose.STEP_UP
        assert kwargs["user_id"] == 7
        assert kwargs["session_id"] == SESSION_ID
        assert kwargs["action"] == StepUpAction.ACCOUNT_DELETE
        assert kwargs["code_challenge"] == CHALLENGE
        assert kwargs["code_challenge_method"] == "S256"
        assert kwargs["redirect_path"] == "/settings/security"
        assert kwargs["client_type"] == "web"
        assert kwargs["browser_binding_hash"] == core_hashing.sha256_hex(staged.browser_binding)
        assert kwargs["idp_code_verifier"] == staged.idp_code_verifier
        assert staged.purpose == oauth_state_constants.OAuthStatePurpose.STEP_UP

    def test_staging_does_not_commit(self, service):
        db = MagicMock()
        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider", return_value=_idp()),
            patch.object(
                authorization_service.identity_provider_links_integration,
                "get_user_identity_provider_by_user_id_and_idp_id",
                return_value=SimpleNamespace(),
            ),
            patch.object(authorization_service.oauth_state_integration, "create_oauth_state"),
        ):
            service.stage_step_up(7, SESSION_ID, 3, StepUpAction.ACCOUNT_DELETE, CHALLENGE, "/", None, db)

        db.commit.assert_not_called()

    @pytest.mark.parametrize(
        "redirect",
        ["https://evil.example.com/", "//evil.example.com", "endurain://callback", "settings", "/../x", "   ", " /x"],
    )
    def test_only_a_relative_return_path_is_accepted(self, service, redirect):
        with pytest.raises(core_exceptions.InvalidInputError):
            _stage(service, redirect=redirect)

    def test_a_malformed_challenge_is_refused(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            _stage(service, challenge="not a challenge")

    @pytest.mark.parametrize("idp", [None, _idp(enabled=False)], ids=["missing", "disabled"])
    def test_a_missing_or_disabled_provider_is_not_found(self, service, idp):
        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider", return_value=idp),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            service.stage_step_up(7, SESSION_ID, 3, StepUpAction.ACCOUNT_DELETE, CHALLENGE, "/", None, MagicMock())

    def test_a_provider_the_user_has_not_linked_is_not_found(self, service):
        with pytest.raises(core_exceptions.NotFoundError):
            _stage(service, linked=False)

    def test_a_provider_without_an_issuer_cannot_prove_a_fresh_sign_in(self, service):
        with pytest.raises(core_exceptions.InvalidInputError):
            _stage(service, idp=_idp(issuer_url=None))


class TestAuthorizationUrl:
    def _query(self, service, purpose):
        staged = idp_contracts.StagedBrowserFlow(
            idp=_idp(),
            purpose=purpose,
            state_id="state-id",
            nonce="nonce-value",
            idp_code_verifier="v" * 86,
            browser_binding="binding",
        )
        return parse_qs(urlsplit(service.authorization_url(staged)).query)

    def test_a_step_up_asks_for_a_new_sign_in_within_the_freshness_limit(self, service):
        query = self._query(service, oauth_state_constants.OAuthStatePurpose.STEP_UP)

        assert query["prompt"] == ["login"]
        assert query["max_age"] == [str(STEP_UP_MAX_AGE_SECONDS)]
        assert query["state"] == ["state-id"]
        assert query["nonce"] == ["nonce-value"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == [f"{HOST}/api/v1/public/idp/callback/idp"] or query["redirect_uri"]

    def test_a_link_does_not_force_a_new_sign_in(self, service):
        query = self._query(service, oauth_state_constants.OAuthStatePurpose.LINK)

        assert "prompt" not in query
        assert "max_age" not in query

    def test_an_unresolvable_endpoint_is_an_upstream_error(self, service):
        staged = idp_contracts.StagedBrowserFlow(
            idp=_idp(authorization_endpoint=None, issuer_url=None),
            purpose=oauth_state_constants.OAuthStatePurpose.STEP_UP,
            state_id="state-id",
            nonce="nonce",
            idp_code_verifier="v" * 86,
            browser_binding="binding",
        )

        with pytest.raises(core_exceptions.UpstreamError):
            service.authorization_url(staged)
