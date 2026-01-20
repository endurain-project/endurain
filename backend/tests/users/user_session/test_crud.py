import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import users.users_session.crud as users_session_crud
import users.users_session.schema as users_session_schema
import users.users_session.models as users_session_models


class TestGetUserSessions:
    """
    Test suite for get_user_sessions function.
    """

    def test_get_user_sessions_success(self, mock_db):
        """
        Test successful retrieval of sessions for a user.
        """
        # Arrange
        user_id = 1
        mock_session1 = MagicMock(spec=users_session_models.UsersSessions)
        mock_session2 = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_session1,
            mock_session2,
        ]
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_user_sessions(user_id, mock_db)

        # Assert
        assert result == [mock_session1, mock_session2]
        mock_db.execute.assert_called_once()

    def test_get_user_sessions_empty(self, mock_db):
        """
        Test retrieval when no sessions exist for user.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_user_sessions(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_user_sessions_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.get_user_sessions(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetSessionById:
    """
    Test suite for get_session_by_id function.
    """

    def test_get_session_by_id_success(self, mock_db):
        """
        Test successful retrieval of session by ID.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_by_id(session_id, mock_db)

        # Assert
        assert result == mock_session
        mock_db.execute.assert_called_once()

    def test_get_session_by_id_not_found(self, mock_db):
        """
        Test retrieval when session does not exist.
        """
        # Arrange
        session_id = "nonexistent-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_by_id(session_id, mock_db)

        # Assert
        assert result is None

    def test_get_session_by_id_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        session_id = "test-session-id"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.get_session_by_id(session_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetSessionByIdNotExpired:
    """
    Test suite for get_session_by_id_not_expired function.
    """

    def test_get_session_by_id_not_expired_success(self, mock_db):
        """
        Test successful retrieval of unexpired session.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_by_id_not_expired(session_id, mock_db)

        # Assert
        assert result == mock_session
        mock_db.execute.assert_called_once()

    def test_get_session_by_id_not_expired_expired_session(self, mock_db):
        """
        Test retrieval of expired session returns None.
        """
        # Arrange
        session_id = "expired-session-id"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_by_id_not_expired(session_id, mock_db)

        # Assert
        assert result is None

    def test_get_session_by_id_not_expired_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        session_id = "test-session-id"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.get_session_by_id_not_expired(session_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetSessionWithOauthState:
    """
    Test suite for get_session_with_oauth_state function.
    """

    def test_get_session_with_oauth_state_success_no_oauth(self, mock_db):
        """
        Test retrieval of session without OAuth state.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.oauth_state_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_with_oauth_state(session_id, mock_db)

        # Assert
        assert result == (mock_session, None)

    def test_get_session_with_oauth_state_success_with_oauth(self, mock_db):
        """
        Test retrieval of session with OAuth state.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.oauth_state_id = "oauth-state-123"
        mock_oauth_state = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        with patch(
            "users.users_session.crud.oauth_state_crud.get_oauth_state_by_id",
            return_value=mock_oauth_state,
        ):
            # Act
            result = users_session_crud.get_session_with_oauth_state(
                session_id, mock_db
            )

            # Assert
            assert result == (mock_session, mock_oauth_state)

    def test_get_session_with_oauth_state_not_found(self, mock_db):
        """
        Test retrieval when session not found.
        """
        # Arrange
        session_id = "nonexistent-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.get_session_with_oauth_state(session_id, mock_db)

        # Assert
        assert result is None


class TestCreateSession:
    """
    Test suite for create_session function.
    """

    def test_create_session_success(self, mock_db):
        """
        Test successful session creation.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_db_session = MagicMock(spec=users_session_models.UsersSessions)

        with patch.object(
            users_session_models,
            "UsersSessions",
            return_value=mock_db_session,
        ):
            # Act
            result = users_session_crud.create_session(session_data, mock_db)

            # Assert
            assert result == mock_db_session
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_session_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.create_session(session_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestMarkTokensExchanged:
    """
    Test suite for mark_tokens_exchanged function.
    """

    def test_mark_tokens_exchanged_success(self, mock_db):
        """
        Test successful marking of tokens as exchanged.
        """
        # Arrange
        session_id = "test-session-id"
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.oauth_state_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Act
        users_session_crud.mark_tokens_exchanged(session_id, mock_db)

        # Assert
        assert mock_session.tokens_exchanged is True
        mock_db.commit.assert_called_once()

    def test_mark_tokens_exchanged_not_found(self, mock_db):
        """
        Test exception when session not found.
        """
        # Arrange
        session_id = "nonexistent-session"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.mark_tokens_exchanged(session_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail


class TestEditSession:
    """
    Test suite for edit_session function.
    """

    def test_edit_session_success(self, mock_db):
        """
        Test successful session update.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        session_data = users_session_schema.UsersSessionsInternal(
            id="test-session-id",
            user_id=1,
            refresh_token="new-hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=1,
        )

        mock_db_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_session
        mock_db.execute.return_value = mock_result

        # Act
        users_session_crud.edit_session(session_data, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_edit_session_not_found(self, mock_db):
        """
        Test exception when session not found.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        session_data = users_session_schema.UsersSessionsInternal(
            id="nonexistent-session",
            user_id=1,
            refresh_token="hashed-token",
            ip_address="192.168.1.1",
            device_type="PC",
            operating_system="Windows",
            operating_system_version="10",
            browser="Chrome",
            browser_version="120.0",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
            token_family_id="family-id",
            rotation_count=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.edit_session(session_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail


class TestDeleteSession:
    """
    Test suite for delete_session function.
    """

    def test_delete_session_success(self, mock_db):
        """
        Test successful session deletion.
        """
        # Arrange
        session_id = "test-session-id"
        user_id = 1
        mock_session = MagicMock(spec=users_session_models.UsersSessions)
        mock_session.token_family_id = "family-id"
        mock_session.oauth_state_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        with patch(
            "users.users_session.crud.users_session_rotated_tokens_crud.delete_by_family",
            return_value=0,
        ):
            # Act
            users_session_crud.delete_session(session_id, user_id, mock_db)

            # Assert
            mock_db.commit.assert_called_once()

    def test_delete_session_not_found(self, mock_db):
        """
        Test exception when session not found.
        """
        # Arrange
        session_id = "nonexistent-session"
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_session_crud.delete_session(session_id, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail


class TestDeleteIdleSessions:
    """
    Test suite for delete_idle_sessions function.
    """

    def test_delete_idle_sessions_success(self, mock_db):
        """
        Test successful deletion of idle sessions.
        """
        # Arrange
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.delete_idle_sessions(cutoff_time, mock_db)

        # Assert
        assert result == 5
        mock_db.commit.assert_called_once()

    def test_delete_idle_sessions_none_deleted(self, mock_db):
        """
        Test when no idle sessions exist.
        """
        # Arrange
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.delete_idle_sessions(cutoff_time, mock_db)

        # Assert
        assert result == 0


class TestDeleteSessionsByFamily:
    """
    Test suite for delete_sessions_by_family function.
    """

    def test_delete_sessions_by_family_success(self, mock_db):
        """
        Test successful deletion of sessions by family.
        """
        # Arrange
        token_family_id = "family-id"
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.delete_sessions_by_family(token_family_id, mock_db)

        # Assert
        assert result == 3
        mock_db.commit.assert_called_once()

    def test_delete_sessions_by_family_none_deleted(self, mock_db):
        """
        Test when no sessions exist for family.
        """
        # Arrange
        token_family_id = "nonexistent-family"
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = users_session_crud.delete_sessions_by_family(token_family_id, mock_db)

        # Assert
        assert result == 0
