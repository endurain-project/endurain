"""Integration tests for users_sessions router endpoints."""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.auth.sessions.router as users_sessions_router
import modules.auth.sessions.schema as users_session_schema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MagicMock:
    """
    Return a mock SQLAlchemy session.

    Returns:
        MagicMock: Mock database session.
    """
    return MagicMock(spec=Session)


@pytest.fixture
def sessions_app(mock_db) -> FastAPI:
    """
    Create a minimal FastAPI app for users_sessions router tests.

    All security dependencies are mocked to allow authenticated
    endpoint testing without real JWTs.

    Args:
        mock_db: Mock database session.

    Returns:
        FastAPI: Configured test application.
    """
    app = FastAPI()
    app.include_router(
        users_sessions_router.router,
        prefix="/sessions",
    )

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None

    return app


@pytest.fixture
def sessions_client(sessions_app: FastAPI) -> TestClient:
    """
    Return a TestClient for the users_sessions test app.

    Args:
        sessions_app: Configured test application.

    Returns:
        TestClient: HTTP test client.
    """
    return TestClient(sessions_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /sessions/user/{user_id}
# ---------------------------------------------------------------------------


class TestReadSessionsUser:
    """Tests for GET /sessions/user/{user_id}."""

    @patch("modules.auth.sessions.router.auth_sessions_crud.get_user_sessions")
    @patch("modules.auth.sessions.router.core_config.settings")
    def test_returns_sessions_list_for_user(
        self,
        mock_settings,
        mock_get_sessions,
        sessions_client,
    ) -> None:
        """
        Returns 200 with list of sessions for the specified user.
        """
        mock_settings.ENVIRONMENT = "production"
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        mock_session = MagicMock(spec=users_session_schema.UsersSessionsRead)
        mock_session.id = "sess-1"
        mock_session.user_id = 5
        mock_session.ip_address = "127.0.0.1"
        mock_session.device_type = "PC"
        mock_session.operating_system = "Linux"
        mock_session.operating_system_version = "5.15"
        mock_session.browser = "Firefox"
        mock_session.browser_version = "120"
        mock_session.created_at = now
        mock_session.last_activity_at = now
        mock_session.expires_at = now + timedelta(days=7)
        mock_get_sessions.return_value = [mock_session]

        response = sessions_client.get("/sessions/user/5")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
        mock_get_sessions.assert_called_once()

    @patch("modules.auth.sessions.router.auth_sessions_crud.get_user_sessions")
    @patch("modules.auth.sessions.router.core_config.settings")
    def test_returns_empty_list_when_user_has_no_sessions(
        self,
        mock_settings,
        mock_get_sessions,
        sessions_client,
    ) -> None:
        """
        Returns 200 with an empty list when the user has no sessions.
        """
        mock_settings.ENVIRONMENT = "production"
        mock_get_sessions.return_value = []

        response = sessions_client.get("/sessions/user/42")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @patch("modules.auth.sessions.router.core_config.settings")
    def test_returns_empty_list_in_demo_environment(
        self,
        mock_settings,
        sessions_client,
    ) -> None:
        """
        Returns 200 with an empty list in demo environment without
        querying the database.
        """
        mock_settings.ENVIRONMENT = "demo"

        response = sessions_client.get("/sessions/user/1")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @patch("modules.auth.sessions.router.auth_sessions_crud.get_user_sessions")
    @patch("modules.auth.sessions.router.core_config.settings")
    def test_propagates_database_error_as_500(
        self,
        mock_settings,
        mock_get_sessions,
        sessions_client,
    ) -> None:
        """
        Propagates HTTPException raised by the CRUD layer.
        """
        mock_settings.ENVIRONMENT = "production"
        mock_get_sessions.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )

        response = sessions_client.get("/sessions/user/1")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}/user/{user_id}
# ---------------------------------------------------------------------------


class TestDeleteSessionUser:
    """Tests for DELETE /sessions/{session_id}/user/{user_id}."""

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_session")
    def test_delete_session_success_returns_204(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Returns 204 No Content when the session is successfully deleted.
        """
        mock_delete.return_value = None

        response = sessions_client.delete("/sessions/session-abc/user/1")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_session")
    def test_delete_nonexistent_session_returns_404(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Returns 404 when the session does not exist.
        """
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

        response = sessions_client.delete("/sessions/no-such-session/user/1")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_session")
    def test_delete_session_for_different_user_propagates_error(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Propagates error when attempting to delete a session that
        belongs to a different user.
        """
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

        response = sessions_client.delete("/sessions/session-abc/user/99")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_session")
    def test_delete_session_calls_crud_with_correct_args(
        self,
        mock_delete,
        sessions_client,
        mock_db,
    ) -> None:
        """
        Ensures delete_session is called with the correct session_id,
        user_id, and db parameters.
        """
        mock_delete.return_value = None

        sessions_client.delete("/sessions/my-session-id/user/7")

        mock_delete.assert_called_once_with("my-session-id", 7, mock_db)

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_session")
    def test_delete_session_database_error_returns_500(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Returns 500 when the CRUD layer raises an internal error.
        """
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )

        response = sessions_client.delete("/sessions/session-abc/user/1")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# DELETE /sessions/user/{user_id}
# ---------------------------------------------------------------------------


class TestDeleteSessionsUser:
    """Tests for DELETE /sessions/user/{user_id}."""

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_sessions_by_user")
    def test_delete_all_sessions_success_returns_204(
        self,
        mock_delete,
        sessions_client,
        mock_db,
    ) -> None:
        """
        Returns 204 No Content and revokes every session for the user
        when no exclusion is supplied (admin-style "revoke all").
        """
        mock_delete.return_value = 3

        response = sessions_client.delete("/sessions/user/7")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(7, mock_db, exclude_session_id=None)

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_sessions_by_user")
    def test_delete_sessions_excludes_current_session(
        self,
        mock_delete,
        sessions_client,
        mock_db,
    ) -> None:
        """
        Forwards the exclude_session_id query parameter so the caller's
        current session is left intact ("revoke other sessions").
        """
        mock_delete.return_value = 2

        response = sessions_client.delete(
            "/sessions/user/7",
            params={"exclude_session_id": "keep-this-session"},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(
            7,
            mock_db,
            exclude_session_id="keep-this-session",
        )

    @patch("modules.auth.sessions.router.auth_sessions_crud.delete_sessions_by_user")
    def test_delete_sessions_database_error_returns_500(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Propagates an internal error raised by the CRUD layer as 500.
        """
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )

        response = sessions_client.delete("/sessions/user/1")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
