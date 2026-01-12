"""Tests for OAuth state utility functions."""

import pytest
from unittest.mock import MagicMock, patch, call

import auth.oauth_state.utils as oauth_state_utils
import auth.oauth_state.crud as oauth_state_crud


class TestCreateStateIdAndNonce:
    """Test suite for create_state_id_and_nonce function."""

    def test_create_state_id_and_nonce_returns_tuple(self):
        """Test that function returns a tuple of two strings."""
        # Act
        result = oauth_state_utils.create_state_id_and_nonce()

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 2
        state_id, nonce = result
        assert isinstance(state_id, str)
        assert isinstance(nonce, str)

    def test_create_state_id_and_nonce_unique_values(self):
        """Test that each call generates unique state_id and nonce."""
        # Act
        results = [oauth_state_utils.create_state_id_and_nonce() for _ in range(10)]

        state_ids = [r[0] for r in results]
        nonces = [r[1] for r in results]

        # Assert - All state_ids should be unique
        assert len(set(state_ids)) == 10
        # Assert - All nonces should be unique
        assert len(set(nonces)) == 10

    def test_create_state_id_and_nonce_different_values(self):
        """Test that state_id and nonce are different from each other."""
        # Act
        state_id, nonce = oauth_state_utils.create_state_id_and_nonce()

        # Assert
        assert state_id != nonce

    def test_create_state_id_and_nonce_url_safe(self):
        """Test that generated values are URL-safe."""
        # Act
        state_id, nonce = oauth_state_utils.create_state_id_and_nonce()

        # Assert - URL-safe base64 characters only
        import re

        url_safe_pattern = re.compile(r"^[A-Za-z0-9_-]+$")
        assert url_safe_pattern.match(state_id)
        assert url_safe_pattern.match(nonce)

    def test_create_state_id_and_nonce_sufficient_length(self):
        """Test that generated values have sufficient entropy (32 bytes = ~43 chars)."""
        # Act
        state_id, nonce = oauth_state_utils.create_state_id_and_nonce()

        # Assert - secrets.token_urlsafe(32) produces ~43 character strings
        assert len(state_id) >= 40
        assert len(nonce) >= 40


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
