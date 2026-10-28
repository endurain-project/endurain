"""Tests for identity-provider token maintenance integration operations."""

from unittest.mock import MagicMock, patch

import modules.auth.identity_providers.service as idp_service_module
from modules.auth.identity_providers import integration_service
from modules.auth.identity_providers.service import IdentityProviderService, TokenAction


def test_refresh_tokens_delegates_to_request_scoped_service(mock_db):
    with patch.object(integration_service, "_service") as service_factory:
        integration_service.refresh_idp_tokens_if_needed(7, mock_db)
    service_factory.return_value.refresh_idp_tokens_if_needed.assert_called_once_with(7, mock_db)


def test_clear_tokens_delegates_with_remote_revoke_option(mock_db):
    with patch.object(integration_service, "_service") as service_factory:
        integration_service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    service_factory.return_value.clear_all_idp_tokens.assert_called_once_with(7, mock_db, True)


def test_service_refreshes_only_links_with_refresh_action(mock_db):
    service = IdentityProviderService(MagicMock(), "https://app.example", "test")
    links = [MagicMock(idp_id=3), MagicMock(idp_id=4), MagicMock(idp_id=5)]
    service._should_refresh_idp_token = MagicMock(
        side_effect=[TokenAction.SKIP, TokenAction.REFRESH, TokenAction.CLEAR]
    )
    service.refresh_idp_session = MagicMock()
    with (
        patch.object(
            idp_service_module.auth_identity_links_crud,
            "get_user_identity_providers_by_user_id",
            return_value=links,
        ),
        patch.object(
            idp_service_module.auth_identity_links_crud,
            "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
        ) as clear,
    ):
        service.refresh_idp_tokens_if_needed(7, mock_db)
    service.refresh_idp_session.assert_called_once_with(7, 4, mock_db)
    clear.assert_called_once_with(7, 5, mock_db)


def test_service_clears_tokens_after_failed_remote_revocation(mock_db):
    service = IdentityProviderService(MagicMock(), "https://app.example", "test")
    service.revoke_idp_token = MagicMock(side_effect=RuntimeError("offline"))
    with (
        patch.object(
            idp_service_module.auth_identity_links_crud,
            "get_user_identity_providers_by_user_id",
            return_value=[MagicMock(idp_id=3)],
        ),
        patch.object(
            idp_service_module.auth_identity_links_crud,
            "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
        ) as clear,
    ):
        service.clear_all_idp_tokens(7, mock_db, revoke_at_idp=True)
    service.revoke_idp_token.assert_called_once_with(7, 3, mock_db)
    clear.assert_called_once_with(7, 3, mock_db)
