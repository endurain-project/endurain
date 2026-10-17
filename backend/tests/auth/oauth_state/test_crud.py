"""Tests for OAuth state CRUD operations."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.sessions.models as users_session_models


class TestGetOAuthStateById:
    """Test suite for get_oauth_state_by_id_and_not_used function."""

    def test_get_oauth_state_by_id_and_not_used_success(self, mock_db):
        """Test successful retrieval of valid OAuth state."""
        # Arrange
        state_id = "test_state_12345678"
        mock_oauth_state = MagicMock(spec=oauth_state_models.OAuthState)
        mock_oauth_state.id = state_id
        mock_oauth_state.expires_at = datetime.now(UTC) + timedelta(minutes=5)
        mock_oauth_state.used = False

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_oauth_state

        # Act
        result = oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, mock_db)

        # Assert
        assert result == mock_oauth_state
        mock_db.execute.assert_called_once()

    def test_get_oauth_state_not_found(self, mock_db):
        """Test OAuth state not found returns None."""
        # Arrange
        state_id = "nonexistent_state"

        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, mock_db)

        # Assert
        assert result is None

    def test_get_oauth_state_expired(self, mock_db):
        """Test expired OAuth state returns None (filtering done in SQL WHERE)."""
        # Arrange
        state_id = "expired_state_12345678"

        # The SQL WHERE clause filters expired states, so execute returns None
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, mock_db)

        # Assert
        assert result is None

    def test_get_oauth_state_already_used(self, mock_db):
        """Test already used OAuth state returns None (replay protection)."""
        # Arrange
        state_id = "used_state_12345678"

        # The SQL WHERE clause filters used states, so execute returns None
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, mock_db)

        # Assert
        assert result is None


class TestGetOAuthStateBySessionId:
    """Test suite for get_oauth_state_by_session_id function."""

    def test_get_oauth_state_by_session_id_success(self, mock_db):
        """Test successful retrieval of OAuth state via session."""
        # Arrange
        session_id = "session_123"
        oauth_state_id = "state_456"

        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.id = session_id
        mock_session.oauth_state_id = oauth_state_id

        mock_oauth_state = MagicMock(spec=oauth_state_models.OAuthState)
        mock_oauth_state.id = oauth_state_id

        # Two execute calls: first for session lookup, second for oauth state lookup
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_session,
            mock_oauth_state,
        ]

        # Act
        result = oauth_state_crud.get_oauth_state_by_session_id(session_id, mock_db)

        # Assert
        assert result == mock_oauth_state

    def test_get_oauth_state_session_not_found(self, mock_db):
        """Test OAuth state retrieval when session doesn't exist."""
        # Arrange
        session_id = "nonexistent_session"

        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = oauth_state_crud.get_oauth_state_by_session_id(session_id, mock_db)

        # Assert
        assert result is None

    def test_get_oauth_state_no_oauth_state_id(self, mock_db):
        """Test OAuth state retrieval when session has no oauth_state_id."""
        # Arrange
        session_id = "session_without_oauth"

        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.id = session_id
        mock_session.oauth_state_id = None

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_session

        # Act
        result = oauth_state_crud.get_oauth_state_by_session_id(session_id, mock_db)

        # Assert
        assert result is None


class TestCreateOAuthState:
    """Test suite for create_oauth_state function."""

    def test_create_oauth_state_minimal(self, mock_db):
        """Test OAuth state creation with minimal required fields."""
        # Arrange
        state_id = "test_state_12345678"
        idp_id = 1
        nonce = "test_nonce_123"
        client_type = "web"
        ip_address = "192.168.1.1"

        with patch("modules.auth.oauth_state.crud.oauth_state_models.OAuthState") as mock_model:
            mock_oauth_state = MagicMock()
            mock_model.return_value = mock_oauth_state

            # Act
            result = oauth_state_crud.create_oauth_state(
                mock_db,
                state_id=state_id,
                idp_id=idp_id,
                nonce=nonce,
                client_type=client_type,
                ip_address=ip_address,
            )

            # Assert
            mock_model.assert_called_once()
            mock_db.add.assert_called_once_with(mock_oauth_state)
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once_with(mock_oauth_state)
            assert result == mock_oauth_state

    def test_create_oauth_state_with_pkce(self, mock_db):
        """Test OAuth state creation with PKCE for mobile."""
        # Arrange
        state_id = "mobile_state_12345678"
        idp_id = 1
        nonce = "test_nonce_123"
        client_type = "mobile"
        ip_address = "192.168.1.1"
        code_challenge = "test_challenge"
        code_challenge_method = "S256"

        with patch("modules.auth.oauth_state.crud.oauth_state_models.OAuthState") as mock_model:
            mock_oauth_state = MagicMock()
            mock_model.return_value = mock_oauth_state

            # Act
            result = oauth_state_crud.create_oauth_state(
                mock_db,
                state_id=state_id,
                idp_id=idp_id,
                nonce=nonce,
                client_type=client_type,
                ip_address=ip_address,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            )

            # Assert
            assert result == mock_oauth_state
            call_kwargs = mock_model.call_args[1]
            assert call_kwargs["code_challenge"] == code_challenge
            assert call_kwargs["code_challenge_method"] == code_challenge_method

    def test_create_oauth_state_with_user_id(self, mock_db):
        """Test OAuth state creation with user_id for link mode."""
        # Arrange
        state_id = "link_state_12345678"
        idp_id = 1
        nonce = "test_nonce_123"
        client_type = "web"
        ip_address = "192.168.1.1"
        user_id = 42

        with patch("modules.auth.oauth_state.crud.oauth_state_models.OAuthState") as mock_model:
            mock_oauth_state = MagicMock()
            mock_model.return_value = mock_oauth_state

            # Act
            result = oauth_state_crud.create_oauth_state(
                mock_db,
                state_id=state_id,
                idp_id=idp_id,
                nonce=nonce,
                client_type=client_type,
                ip_address=ip_address,
                user_id=user_id,
            )

            # Assert
            assert result == mock_oauth_state
            call_kwargs = mock_model.call_args[1]
            assert call_kwargs["user_id"] == user_id

    def test_create_oauth_state_sets_expiry(self, mock_db):
        """Test OAuth state creation sets 10-minute expiry."""
        # Arrange
        state_id = "expiry_test_state"
        idp_id = 1
        nonce = "test_nonce_123"
        client_type = "web"
        ip_address = "192.168.1.1"

        with patch("modules.auth.oauth_state.crud.oauth_state_models.OAuthState") as mock_model:
            mock_oauth_state = MagicMock()
            mock_model.return_value = mock_oauth_state

            # Act
            oauth_state_crud.create_oauth_state(
                mock_db,
                state_id=state_id,
                idp_id=idp_id,
                nonce=nonce,
                client_type=client_type,
                ip_address=ip_address,
            )

            # Assert
            call_kwargs = mock_model.call_args[1]
            expires_at = call_kwargs["expires_at"]
            now = datetime.now(UTC)
            expected_expiry = now + timedelta(minutes=10)

            # Allow 5 second tolerance for test execution time
            time_diff = abs((expires_at - expected_expiry).total_seconds())
            assert time_diff < 5


class TestMarkOAuthStateUsed:
    """Test suite for mark_oauth_state_used function."""

    def test_mark_oauth_state_used_success(self, mock_db):
        """Test successful marking of OAuth state as used."""
        # Arrange
        state_id = "test_state_12345678"

        mock_db.execute.return_value.rowcount = 1

        # Act
        result = oauth_state_crud.mark_oauth_state_used(state_id, mock_db)

        # Assert
        assert result is True
        mock_db.commit.assert_called_once()

    def test_mark_oauth_state_used_not_found(self, mock_db):
        """Test marking non-existent OAuth state returns False."""
        # Arrange
        state_id = "nonexistent_state"

        mock_db.execute.return_value.rowcount = 0

        # Act
        result = oauth_state_crud.mark_oauth_state_used(state_id, mock_db)

        # Assert
        assert result is False
        mock_db.commit.assert_called_once()


class TestDeleteOAuthState:
    """Test suite for delete_oauth_state function."""

    def test_delete_oauth_state_success(self, mock_db):
        """Test successful deletion of OAuth state."""
        # Arrange
        oauth_state_id = "test_state_12345678"
        expected_count = 1

        mock_db.execute.return_value.rowcount = expected_count

        # Act
        result = oauth_state_crud.delete_oauth_state(oauth_state_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.commit.assert_called_once()

    def test_delete_oauth_state_not_found(self, mock_db):
        """Test deletion when OAuth state doesn't exist."""
        # Arrange
        oauth_state_id = "nonexistent_state"

        mock_db.execute.return_value.rowcount = 0

        # Act
        result = oauth_state_crud.delete_oauth_state(oauth_state_id, mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_oauth_state_exception(self, mock_db):
        """Test exception handling in delete_oauth_state."""
        # Arrange
        oauth_state_id = "error_state"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            oauth_state_crud.delete_oauth_state(oauth_state_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in exc_info.value.detail


class TestDeleteExpiredOAuthStates:
    """Test suite for delete_expired_oauth_states function."""

    def test_delete_expired_oauth_states_success(self, mock_db):
        """Test successful deletion of expired OAuth states."""
        # Arrange
        expected_count = 5

        mock_db.execute.return_value.rowcount = expected_count

        # Act
        result = oauth_state_crud.delete_expired_oauth_states(mock_db)

        # Assert
        assert result == expected_count
        mock_db.commit.assert_called_once()

    def test_delete_expired_oauth_states_none_found(self, mock_db):
        """Test deletion when no expired states exist."""
        # Arrange
        mock_db.execute.return_value.rowcount = 0

        # Act
        result = oauth_state_crud.delete_expired_oauth_states(mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_expired_oauth_states_cutoff(self, mock_db):
        """Test expired states are deleted via SQL WHERE clause."""
        # Arrange
        mock_db.execute.return_value.rowcount = 0

        # Act
        result = oauth_state_crud.delete_expired_oauth_states(mock_db)

        # Assert
        assert result == 0
        mock_db.execute.assert_called_once()
