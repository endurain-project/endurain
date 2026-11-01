"""The SSO callback audits a new identity link."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing

import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.oauth_state.constants as oauth_state_constants


def _service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), "https://app.example.com")


def test_linking_a_provider_is_audited_with_the_provider_id(mock_db):
    service = _service()
    idp = MagicMock(id=3, slug="idp", provider_type="oauth2", issuer_url=None, userinfo_endpoint="https://x/userinfo")
    idp.name = "GitHub"
    idp.sync_user_info = False
    oauth_state = MagicMock(
        user_id=7, purpose=oauth_state_constants.OAuthStatePurpose.LINK, nonce="n", redirect_path="/", client_type="web"
    )
    oauth_client = MagicMock()
    oauth_client.fetch_token.return_value = {"access_token": "at"}
    user = MagicMock(id=7, username="alice")
    with (
        patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
        patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
        patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
        patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
        patch.object(service._oidc, "get_userinfo", return_value={"sub": "s"}),
        patch.object(callback_service.users_integration, "get_user", return_value=user),
        patch.object(
            callback_service.identity_provider_links_integration,
            "get_user_identity_provider_by_subject_and_idp_id",
            return_value=None,
        ),
        patch.object(callback_service.identity_provider_links_integration, "create_user_identity_provider"),
        patch.object(callback_service.idp_event_publishers, "publish_idp_linked"),
        jasil_testing.capture_audit() as audit,
    ):
        service.handle_callback(idp, "code", "state", oauth_state, mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id,
        outcome="success",
        target_type="user",
        target_id="7",
        target_owner_id="7",
    )
    assert entry.details == {"idp_id": 3}
