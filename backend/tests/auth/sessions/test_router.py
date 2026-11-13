"""Integration tests for users_sessions router endpoints."""

import uuid
from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.auth.sessions.router as users_sessions_router
import modules.auth.sessions.schema as users_session_schema
from tests._helpers.auth import MOCK_USER_ID

SESSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000005e1")
VERIFIER = MagicMock()
STEP_UP = {"current_password": "admin-password"}

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
    app.dependency_overrides[auth_dependencies.get_session_revoke_verifier] = lambda: VERIFIER
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)

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
        session = users_session_schema.UserSessionsRead(
            id=SESSION_ID,
            user_id=MOCK_USER_ID,
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
        mock_list.return_value = users_session_schema.UserSessionsPage.build([session], 3, 2, 1)

        response = sessions_client.get(f"/users/{MOCK_USER_ID}/sessions?page_number=2&num_records=1")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(SESSION_ID)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (3, 2, 1, 3)
        assert mock_list.call_args.args[:2] == (MOCK_USER_ID, core_pagination.PageParams(2, 1))

    @patch("modules.auth.sessions.router.sessions_service.list_user_sessions")
    def test_defaults_the_window_and_returns_an_empty_page(self, mock_list, sessions_client) -> None:
        """Omitted paging parameters resolve to the default window."""
        mock_list.return_value = users_session_schema.UserSessionsPage.build([], 0, 1, 25)

        response = sessions_client.get(f"/users/{MOCK_USER_ID}/sessions")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert mock_list.call_args.args[:2] == (MOCK_USER_ID, core_pagination.PageParams(1, 25))

    def test_rejects_an_oversized_page(self, sessions_client) -> None:
        """A page size above the cap is a validation error."""
        response = sessions_client.get(f"/users/{MOCK_USER_ID}/sessions?num_records=201")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("get", "/users/{}/sessions", {}),
            ("post", f"/users/{{}}/sessions/{SESSION_ID}/revoke", {"json": {"step_up": STEP_UP}}),
            ("post", "/users/{}/sessions/revoke", {"json": {"step_up": STEP_UP}}),
        ],
    )
    @pytest.mark.parametrize("malformed", ["0", "7", "not-a-uuid"])
    def test_a_malformed_user_id_is_422(self, sessions_client, method, path, kwargs, malformed) -> None:
        """A user id that is not a UUID is a validation error on every administrator session route."""
        response = getattr(sessions_client, method)(path.format(malformed), **kwargs)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch("modules.auth.sessions.service.core_config.settings")
    def test_returns_an_empty_page_in_demo_environment(self, mock_settings, sessions_client) -> None:
        """Demo hides sessions without querying the database."""
        mock_settings.ENVIRONMENT = "demo"

        response = sessions_client.get(f"/users/{MOCK_USER_ID}/sessions")

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

        response = sessions_client.get(f"/users/{MOCK_USER_ID}/sessions")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# POST /users/{user_id}/sessions/{session_id}/revoke
# ---------------------------------------------------------------------------


class TestRevokeSessionUser:
    """Tests for POST /users/{user_id}/sessions/{session_id}/revoke."""

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_revoke_returns_204_and_hands_the_service_the_step_up_and_verifier(
        self, mock_delete, sessions_client, mock_db
    ) -> None:
        """The service gets the ids, the step-up without wrapper, the verifier and the session."""
        response = sessions_client.post(
            f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}/revoke", json={"step_up": STEP_UP}
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(
            SESSION_ID,
            MOCK_USER_ID,
            auth_schema.StepUpVerification(current_password="admin-password"),
            VERIFIER,
            mock_db,
        )

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_revoke_without_a_step_up_is_422_and_never_reaches_the_service(self, mock_delete, sessions_client) -> None:
        """An empty body, or a body without step_up, is refused before the service."""
        assert sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}/revoke", json={}).status_code == 422
        assert sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}/revoke").status_code == 422
        mock_delete.assert_not_called()

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_a_refused_step_up_is_403_step_up_failed(self, mock_delete, sessions_client) -> None:
        """The service's step-up refusal is a 403 problem."""
        mock_delete.side_effect = core_exceptions.StepUpFailedError()

        response = sessions_client.post(
            f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}/revoke", json={"step_up": STEP_UP}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_a_missing_session_is_404(self, mock_delete, sessions_client) -> None:
        """A session that is not the user's is not found."""
        mock_delete.side_effect = core_exceptions.NotFoundError("Session not found")

        response = sessions_client.post(
            f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}/revoke", json={"step_up": STEP_UP}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sessions.router.sessions_service.delete_session")
    def test_a_malformed_session_id_is_422_and_never_reaches_the_service(self, mock_delete, sessions_client) -> None:
        """A session id that is not a UUID is refused before the service."""
        response = sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/not-a-uuid/revoke", json={"step_up": STEP_UP})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        mock_delete.assert_not_called()

    def test_the_delete_route_is_gone(self, sessions_client) -> None:
        """DELETE on the session is not served any more."""
        assert (
            sessions_client.delete(f"/users/{MOCK_USER_ID}/sessions/{SESSION_ID}").status_code
            == status.HTTP_404_NOT_FOUND
        )


# ---------------------------------------------------------------------------
# POST /users/{user_id}/sessions/revoke
# ---------------------------------------------------------------------------


class TestRevokeSessionsUser:
    """Tests for POST /users/{user_id}/sessions/revoke."""

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
    def test_revoke_all_returns_204_without_an_exclusion(self, mock_delete, sessions_client, mock_db) -> None:
        """Every session goes when no exclusion is supplied."""
        response = sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/revoke", json={"step_up": STEP_UP})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(
            MOCK_USER_ID,
            auth_schema.StepUpVerification(current_password="admin-password"),
            VERIFIER,
            mock_db,
            exclude_session_id=None,
        )

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
    def test_a_malformed_excluded_session_id_is_422(self, mock_delete, sessions_client) -> None:
        """An exclude_session_id that is not a UUID is refused before the service."""
        response = sessions_client.post(
            f"/users/{MOCK_USER_ID}/sessions/revoke",
            params={"exclude_session_id": "not-a-uuid"},
            json={"step_up": STEP_UP},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        mock_delete.assert_not_called()

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
    def test_revoke_forwards_the_excluded_session(self, mock_delete, sessions_client, mock_db) -> None:
        """The exclude_session_id query parameter leaves that session intact."""
        response = sessions_client.post(
            f"/users/{MOCK_USER_ID}/sessions/revoke",
            params={"exclude_session_id": str(SESSION_ID)},
            json={"step_up": STEP_UP},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert mock_delete.call_args.kwargs == {"exclude_session_id": SESSION_ID}

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
    def test_revoke_without_a_step_up_is_422_and_never_reaches_the_service(self, mock_delete, sessions_client) -> None:
        """A missing step_up is refused before the service."""
        assert sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/revoke", json={}).status_code == 422
        mock_delete.assert_not_called()

    @patch("modules.auth.sessions.router.sessions_service.delete_sessions_by_user_and_commit")
    def test_a_refused_step_up_is_403_step_up_failed(self, mock_delete, sessions_client) -> None:
        """The service's step-up refusal is a 403 problem."""
        mock_delete.side_effect = core_exceptions.StepUpFailedError()

        response = sessions_client.post(f"/users/{MOCK_USER_ID}/sessions/revoke", json={"step_up": STEP_UP})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["type"] == "urn:endurain:error:step-up-failed"

    def test_the_delete_route_is_gone(self, sessions_client) -> None:
        """DELETE on the sessions collection is not served any more."""
        assert (
            sessions_client.delete(f"/users/{MOCK_USER_ID}/sessions").status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        )
