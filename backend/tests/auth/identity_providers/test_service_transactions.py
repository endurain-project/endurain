"""The identity-provider service owns the commit of the OAuth state it creates and consumes."""

from unittest.mock import MagicMock, patch

import modules.auth.identity_providers.service as idp_service_module


def _service() -> idp_service_module.IdentityProviderService:
    return idp_service_module.IdentityProviderService(MagicMock(), "https://endurain.test", "v1")


def test_a_login_oauth_state_is_committed_before_the_browser_is_redirected(mock_db):
    with (
        patch.object(idp_service_module.oauth_state_integration, "create_state_id_and_nonce", return_value=("s", "n")),
        patch.object(idp_service_module.oauth_state_integration, "create_oauth_state") as create,
    ):
        state_id = _service().create_login_oauth_state(
            3,
            client_type="web",
            ip_address="127.0.0.1",
            redirect_path=None,
            code_challenge="c" * 43,
            code_challenge_method="S256",
            db=mock_db,
        )

    assert state_id == "s"
    assert create.call_args.kwargs["idp_id"] == 3
    mock_db.commit.assert_called_once()


def test_a_claim_is_committed_even_when_another_callback_won(mock_db):
    with patch.object(idp_service_module.oauth_state_integration, "mark_oauth_state_used", return_value=False):
        assert _service().claim_oauth_state("s", mock_db) is False

    mock_db.commit.assert_called_once()
