"""Tests for OAuth state utility functions."""

import pytest
from unittest.mock import MagicMock, patch, call

import auth.oauth_state.utils as oauth_state_utils
import auth.oauth_state.crud as oauth_state_crud


class TestDeleteExpiredOAuthStatesFromDb:
    """Test suite for delete_expired_oauth_states_from_db function."""

    def test_delete_expired_oauth_states_with_deletions(self):
        """Test cleanup when expired states exist."""
        # Arrange
        num_deleted = 5
        mock_db = MagicMock()

        with patch(
            "auth.oauth_state.utils.SessionLocal"
        ) as mock_session_local, patch.object(
            oauth_state_crud, "delete_expired_oauth_states", return_value=num_deleted
        ) as mock_delete:

            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            oauth_state_utils.delete_expired_oauth_states_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)
            mock_session_local.assert_called_once()

    def test_delete_expired_oauth_states_no_deletions(self):
        """Test cleanup when no expired states exist."""
        # Arrange
        num_deleted = 0
        mock_db = MagicMock()

        with patch(
            "auth.oauth_state.utils.SessionLocal"
        ) as mock_session_local, patch.object(
            oauth_state_crud, "delete_expired_oauth_states", return_value=num_deleted
        ) as mock_delete:

            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            oauth_state_utils.delete_expired_oauth_states_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)

    def test_delete_expired_oauth_states_exception_handling(self):
        """Test exception handling in cleanup function."""
        # Arrange
        mock_db = MagicMock()

        with patch(
            "auth.oauth_state.utils.SessionLocal"
        ) as mock_session_local, patch.object(
            oauth_state_crud,
            "delete_expired_oauth_states",
            side_effect=Exception("Database error"),
        ):

            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act & Assert
            with pytest.raises(Exception, match="Database error"):
                oauth_state_utils.delete_expired_oauth_states_from_db()

    def test_delete_expired_oauth_states_context_manager(self):
        """Test session context manager is properly used."""
        # Arrange
        num_deleted = 3
        mock_db = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_db
        mock_context.__exit__.return_value = None

        with patch(
            "auth.oauth_state.utils.SessionLocal", return_value=mock_context
        ) as mock_session_local, patch.object(
            oauth_state_crud, "delete_expired_oauth_states", return_value=num_deleted
        ):

            # Act
            oauth_state_utils.delete_expired_oauth_states_from_db()

            # Assert
            mock_session_local.assert_called_once()
            mock_context.__enter__.assert_called_once()
            mock_context.__exit__.assert_called_once()
