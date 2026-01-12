"""
Tests for identity_providers.utils module - IdP token refresh/clear functions.

This module tests the utility functions for managing IdP tokens,
including refresh_idp_tokens_if_needed and clear_all_idp_tokens.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.orm import Session

import auth.identity_providers.utils as idp_utils


class TestRefreshIdpTokensIfNeeded:
    """Test suite for refresh_idp_tokens_if_needed function."""

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_no_links(self):
        """Test when user has no IdP links."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[],
        ):
            # Act - should return early without errors
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - no exceptions raised

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_skip_action(self):
        """Test when token doesn't need refresh (SKIP action)."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1
        mock_link.user_id = user_id

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh:
            from auth.identity_providers.service import TokenAction

            mock_should_refresh.return_value = TokenAction.SKIP

            # Act
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - should check but not refresh
            mock_should_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_refresh_success(self):
        """Test successful token refresh."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1
        mock_link.user_id = user_id

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh, patch(
            "auth.identity_providers.utils.idp_service.idp_service.refresh_idp_session",
            new_callable=AsyncMock,
        ) as mock_refresh:
            from auth.identity_providers.service import TokenAction

            mock_should_refresh.return_value = TokenAction.REFRESH
            mock_refresh.return_value = True

            # Act
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert
            mock_refresh.assert_called_once_with(user_id, mock_link.idp_id, mock_db)

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_refresh_failure(self):
        """Test when token refresh fails."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1
        mock_link.user_id = user_id

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh, patch(
            "auth.identity_providers.utils.idp_service.idp_service.refresh_idp_session",
            new_callable=AsyncMock,
        ) as mock_refresh:
            from auth.identity_providers.service import TokenAction

            mock_should_refresh.return_value = TokenAction.REFRESH
            mock_refresh.return_value = False  # Refresh failed

            # Act - should not raise exception
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - failure logged but no exception
            mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_clear_action(self):
        """Test when token needs to be cleared (expired)."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1
        mock_link.user_id = user_id

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh, patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            from auth.identity_providers.service import TokenAction

            mock_should_refresh.return_value = TokenAction.CLEAR
            mock_clear.return_value = True

            # Act
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert
            mock_clear.assert_called_once_with(user_id, mock_link.idp_id, mock_db)

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_clear_failure(self):
        """Test when clearing token fails."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh, patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            from auth.identity_providers.service import TokenAction

            mock_should_refresh.return_value = TokenAction.CLEAR
            mock_clear.return_value = False  # Clear failed

            # Act - should not raise exception
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - failure logged but no exception
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_individual_idp_error(self):
        """Test that error in one IdP doesn't stop checking others."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link1 = MagicMock()
        mock_link1.idp_id = 1

        mock_link2 = MagicMock()
        mock_link2.idp_id = 2

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link1, mock_link2],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service._should_refresh_idp_token"
        ) as mock_should_refresh:
            from auth.identity_providers.service import TokenAction

            # First IdP raises error, second succeeds
            mock_should_refresh.side_effect = [
                Exception("Error checking IdP 1"),
                TokenAction.SKIP,
            ]

            # Act - should not raise exception
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - both IdPs were attempted
            assert mock_should_refresh.call_count == 2

    @pytest.mark.asyncio
    async def test_refresh_idp_tokens_if_needed_database_error(self):
        """Test error when retrieving IdP links."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            side_effect=Exception("Database connection error"),
        ):
            # Act - should not raise exception
            await idp_utils.refresh_idp_tokens_if_needed(user_id, mock_db)

            # Assert - error logged but not raised


class TestClearAllIdpTokens:
    """Test suite for clear_all_idp_tokens function."""

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_no_links(self):
        """Test when user has no IdP links."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[],
        ):
            # Act - should return early
            await idp_utils.clear_all_idp_tokens(user_id, mock_db)

            # Assert - no exceptions raised

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_without_revocation(self):
        """Test clearing tokens without IdP revocation."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            mock_clear.return_value = True

            # Act
            await idp_utils.clear_all_idp_tokens(user_id, mock_db, revoke_at_idp=False)

            # Assert
            mock_clear.assert_called_once_with(user_id, mock_link.idp_id, mock_db)

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_with_revocation_success(self):
        """Test clearing tokens with successful IdP revocation."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service.revoke_idp_token",
            new_callable=AsyncMock,
        ) as mock_revoke, patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            mock_revoke.return_value = True
            mock_clear.return_value = True

            # Act
            await idp_utils.clear_all_idp_tokens(user_id, mock_db, revoke_at_idp=True)

            # Assert
            mock_revoke.assert_called_once_with(user_id, mock_link.idp_id, mock_db)
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_with_revocation_failure(self):
        """Test clearing tokens when IdP revocation fails."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service.revoke_idp_token",
            new_callable=AsyncMock,
        ) as mock_revoke, patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            mock_revoke.return_value = False  # Revocation failed
            mock_clear.return_value = True

            # Act - should still clear locally
            await idp_utils.clear_all_idp_tokens(user_id, mock_db, revoke_at_idp=True)

            # Assert - local clearing still happens
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_revocation_exception(self):
        """Test that revocation exception doesn't prevent local clearing."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.idp_service.idp_service.revoke_idp_token",
            new_callable=AsyncMock,
        ) as mock_revoke, patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            mock_revoke.side_effect = Exception("Revocation error")
            mock_clear.return_value = True

            # Act - should not raise exception
            await idp_utils.clear_all_idp_tokens(user_id, mock_db, revoke_at_idp=True)

            # Assert - local clearing still happens despite revocation error
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_clear_failure(self):
        """Test when local clearing returns False."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link = MagicMock()
        mock_link.idp_id = 1

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link],
        ), patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            mock_clear.return_value = False  # No token to clear

            # Act - should not raise exception
            await idp_utils.clear_all_idp_tokens(user_id, mock_db)

            # Assert - logged but no exception
            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_individual_idp_error(self):
        """Test that error clearing one IdP doesn't stop clearing others."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_link1 = MagicMock()
        mock_link1.idp_id = 1

        mock_link2 = MagicMock()
        mock_link2.idp_id = 2

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            return_value=[mock_link1, mock_link2],
        ), patch(
            "auth.identity_providers.utils.user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id"
        ) as mock_clear:
            # First IdP raises error, second succeeds
            mock_clear.side_effect = [Exception("Error clearing IdP 1"), True]

            # Act - should not raise exception
            await idp_utils.clear_all_idp_tokens(user_id, mock_db)

            # Assert - both IdPs were attempted
            assert mock_clear.call_count == 2

    @pytest.mark.asyncio
    async def test_clear_all_idp_tokens_database_error(self):
        """Test error when retrieving IdP links during logout."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        with patch(
            "auth.identity_providers.utils.user_idp_crud.get_user_identity_providers_by_user_id",
            side_effect=Exception("Database error during logout"),
        ):
            # Act - should not raise exception
            await idp_utils.clear_all_idp_tokens(user_id, mock_db)

            # Assert - error logged but not raised (logout should proceed)
