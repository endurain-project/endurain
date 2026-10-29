"""Integration tests for users_sessions router endpoints."""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
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
        prefix="/users",
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
# GET /users/{user_id}/sessions
# ---------------------------------------------------------------------------


class TestReadSessionsUser:
    """Tests for GET /users/{user_id}/sessions."""

    @patch("modules.auth.sessions.router.sessions_service.list_user_sessions")
    def test_returns_a_page_of_sessions_for_user(self, mock_list, sessions_client) -> None:
        """Returns the page envelope and forwards the window."""
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        session = users_session_schema.UsersSessionsRead(
            id="sess-1",
            user_id=5,
            ip_address="127.0.0.1",
            device_type="PC",
            operating_system="Linux",
            operating_system_version="5.15",
            browser="Firefox",
            browser_version="120",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=7),
        )
        mock_list.return_value = users_session_schema.UsersSessionsPage.build([session], 3, 2, 1)

        response = sessions_client.get("/users/5/sessions?page_number=2&num_records=1")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert [item["id"] for item in body["items"]] == ["sess-1"]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (3, 2, 1, 3)
        assert mock_list.call_args.args[:2] == (5, core_pagination.PageParams(2, 1))

    @patch("modules.auth.sessions.router.sessions_service.list_user_sessions")
    def test_defaults_the_window_and_returns_an_empty_page(self, mock_list, sessions_client) -> None:
        """Omitted paging parameters resolve to the default window."""
        mock_list.return_value = users_session_schema.UsersSessionsPage.build([], 0, 1, 25)

        response = sessions_client.get("/users/42/sessions")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert mock_list.call_args.args[:2] == (42, core_pagination.PageParams(1, 25))

    def test_rejects_an_oversized_page(self, sessions_client) -> None:
        """A page size above the cap is a validation error."""
        response = sessions_client.get("/users/1/sessions?num_records=201")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_rejects_a_non_positive_user_id(self, sessions_client) -> None:
        """A user id below 1 is a validation error, as on every other id path."""
        response = sessions_client.get("/users/0/sessions")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch("modules.auth.sessions.service.core_config.settings")
    def test_returns_an_empty_page_in_demo_environment(self, mock_settings, sessions_client) -> None:
        """Demo hides sessions without querying the database."""
        mock_settings.ENVIRONMENT = "demo"

        response = sessions_client.get("/users/1/sessions")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    @patch("modules.auth.sessions.router.sessions_service.list_user_sessions")
    def test_propagates_database_error_as_500(self, mock_list, sessions_client) -> None:
        """Propagates the error raised below the router."""
        mock_list.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )

        response = sessions_client.get("/users/1/sessions")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteSessionUser:
    """Tests for DELETE /users/{user_id}/sessions/{session_id}."""

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_delete_session_success_returns_204(
        self,
        mock_delete,
        sessions_client,
    ) -> None:
        """
        Returns 204 No Content when the session is successfully deleted.
        """
        mock_delete.return_value = None

        response = sessions_client.delete("/users/1/sessions/session-abc")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
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

        response = sessions_client.delete("/users/1/sessions/no-such-session")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
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

        response = sessions_client.delete("/users/99/sessions/session-abc")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
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

        sessions_client.delete("/users/7/sessions/my-session-id")

        mock_delete.assert_called_once_with("my-session-id", 7, mock_db)

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
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

        response = sessions_client.delete("/users/1/sessions/session-abc")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}/sessions
# ---------------------------------------------------------------------------


class TestDeleteSessionsUser:
    """Tests for DELETE /users/{user_id}/sessions."""

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
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

        response = sessions_client.delete("/users/7/sessions")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(7, mock_db, exclude_session_id=None)

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
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
            "/users/7/sessions",
            params={"exclude_session_id": "keep-this-session"},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(
            7,
            mock_db,
            exclude_session_id="keep-this-session",
        )

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
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

        response = sessions_client.delete("/users/1/sessions")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
