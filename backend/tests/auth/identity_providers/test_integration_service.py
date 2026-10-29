"""Tests for the identity-provider operations published to auth peers."""

from unittest.mock import MagicMock, patch

from modules.auth.identity_providers import integration_service


def test_requesting_a_refresh_delegates_to_request_scoped_service(mock_db):
    with patch.object(integration_service.identity_providers_tokens, "IdpTokenService") as token_service:
        integration_service.request_idp_token_refresh(7, mock_db)
    token_service.return_value.request_idp_token_refresh.assert_called_once_with(7, mock_db)


def test_clear_tokens_delegates_with_remote_revoke_option(mock_db):
    with patch.object(integration_service.identity_providers_tokens, "IdpTokenService") as token_service:
        integration_service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    token_service.return_value.clear_all_idp_tokens.assert_called_once_with(7, mock_db, True)


def test_get_identity_provider_delegates_to_crud():
    db = MagicMock()
    provider = MagicMock()
    with patch.object(
        integration_service.identity_providers_crud, "get_identity_provider", return_value=provider
    ) as get:
        result = integration_service.get_identity_provider(7, db)
    get.assert_called_once_with(7, db)
    assert result is provider
