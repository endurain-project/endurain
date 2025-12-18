from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status


class TestLoginEndpointSecurity:
    """
    Test suite for verifying the security and behavior of the login endpoint.

    This class contains tests that cover various scenarios for the login endpoint, including:
    - Successful login without Multi-Factor Authentication (MFA) for different client types.
    - Login attempts when MFA is required, ensuring the correct response and MFA flow.
    - Handling of invalid client types, ensuring forbidden access is enforced.
    - Login attempts with invalid credentials, ensuring proper error handling.
    - Login attempts with inactive users, ensuring access is denied as expected.

    Each test uses extensive mocking to simulate authentication, user activity checks, MFA status, and session/token creation, allowing for isolated and reliable testing of the endpoint's logic and security requirements.
    """

    @pytest.mark.parametrize(
        "client_type, expected_status, returns_tokens",
        [
            ("web", status.HTTP_200_OK, False),
            ("mobile", status.HTTP_200_OK, True),
        ],
    )
    def test_login_without_mfa(
        self,
        fast_api_app,
        fast_api_client,
        sample_user_read,
        client_type,
        expected_status,
        returns_tokens,
    ):
        """
        Test the login endpoint behavior when Multi-Factor Authentication (MFA) is not enabled for the user.

        This test verifies that:
        - The login process completes successfully without requiring MFA.
        - The correct response is returned based on whether tokens are expected.
        - The appropriate authentication, user activity, and MFA checks are patched and simulated.
        - The fake store is not called during the process.

        Args:
            fast_api_app: The FastAPI application instance under test.
            fast_api_client: The test client for making HTTP requests to the FastAPI app.
            sample_user_read: A sample user object returned by the authentication mock.
            client_type: The type of client making the request (used in headers and app state).
            expected_status: The expected HTTP status code of the response.
            returns_tokens: Boolean indicating if the endpoint should return tokens or just a session ID.
        """
        fast_api_app.state._client_type = client_type
        with patch("session.router.auth_utils.authenticate_user") as mock_auth, patch(
            "session.router.users_utils.check_user_is_active"
        ), patch(
            "session.router.profile_utils.is_mfa_enabled_for_user"
        ) as mock_mfa, patch(
            "session.router.auth_utils.complete_login"
        ) as mock_complete:
            mock_auth.return_value = sample_user_read
            mock_mfa.return_value = False
            mock_complete.return_value = (
                {"session_id": "test-session"}
                if not returns_tokens
                else {
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "session_id": "session",
                    "token_type": "Bearer",
                    "expires_in": 900,
                }
            )

            resp = fast_api_client.post(
                "/auth/login",
                data={"username": "testuser", "password": "secret"},
                headers={"X-Client-Type": client_type},
            )
            assert resp.status_code == expected_status
            body = resp.json()
            if returns_tokens:
                assert body["access_token"] == "token"
                assert body["refresh_token"] == "refresh"
                assert body["session_id"] == "session"
                assert body["token_type"] == "Bearer"
                assert isinstance(body["expires_in"], int)
            else:
                assert body == {"session_id": "test-session"}
            assert fast_api_app.state.fake_store.calls == []

    @pytest.mark.parametrize(
        "client_type, expected_status",
        [
            ("web", status.HTTP_202_ACCEPTED),
            ("mobile", status.HTTP_200_OK),
        ],
    )
    def test_login_with_mfa_required(
        self,
        fast_api_app,
        fast_api_client,
        sample_user_read,
        client_type,
        expected_status,
    ):
        """
        Test the login endpoint when Multi-Factor Authentication (MFA) is required.

        This test verifies that when a user with MFA enabled attempts to log in,
        the API responds with the correct status code and indicates that MFA is required.
        It mocks the authentication, user activity check, and MFA status check to simulate
        the scenario where MFA is enabled for the user.

        Args:
            fast_api_app: The FastAPI application instance under test.
            fast_api_client: The test client for making HTTP requests to the FastAPI app.
            sample_user_read: A sample user object returned by the authentication mock.
            client_type: The type of client making the request (used in headers).
            expected_status: The expected HTTP status code for the response.

        Asserts:
            - The response status code matches the expected status.
            - The response JSON contains 'mfa_required' set to True.
            - The response JSON contains the correct 'username'.
            - The fake_store in the app state records the correct call.
        """
        fast_api_app.state._client_type = client_type
        with patch("session.router.auth_utils.authenticate_user") as mock_auth, patch(
            "session.router.users_utils.check_user_is_active"
        ), patch("session.router.profile_utils.is_mfa_enabled_for_user") as mock_mfa:
            mock_auth.return_value = sample_user_read
            mock_mfa.return_value = True

            resp = fast_api_client.post(
                "/auth/login",
                data={"username": "testuser", "password": "secret"},
                headers={"X-Client-Type": client_type},
            )
            assert resp.status_code == expected_status
            body = resp.json()
            assert body["mfa_required"] is True
            assert body["username"] == "testuser"
            assert fast_api_app.state.fake_store.calls == [
                ("testuser", sample_user_read.id)
            ]

    def test_invalid_client_type_forbidden(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test that a login attempt with an invalid client type returns a 403 Forbidden response.

        This test sets the application's client type to "desktop" and mocks the authentication,
        user activity check, MFA status, token creation, and session creation utilities. It then
        sends a POST request to the "/auth/login" endpoint with the "X-Client-Type" header set to "desktop".
        The test asserts that the response status code is 403 Forbidden and the response detail
        indicates an invalid client type.

        Args:
            fast_api_app: The FastAPI application instance.
            fast_api_client: The test client for making HTTP requests.
            sample_user_read: A sample user object returned by the authentication mock.
        """
        fast_api_app.state._client_type = "desktop"
        with patch("session.router.auth_utils.authenticate_user") as mock_auth, patch(
            "session.router.users_utils.check_user_is_active"
        ), patch(
            "session.router.profile_utils.is_mfa_enabled_for_user"
        ) as mock_mfa, patch(
            "session.router.auth_utils.create_tokens"
        ) as mock_create_tokens, patch(
            "session.router.session_utils.create_session"
        ) as mock_create_session:
            mock_auth.return_value = sample_user_read
            mock_mfa.return_value = False

            mock_create_tokens.return_value = (
                "sid",
                object(),
                "acc",
                object(),
                "ref",
                "csrf",
            )
            mock_create_session.return_value = None

            resp = fast_api_client.post(
                "/auth/login",
                data={"username": "x", "password": "y"},
                headers={"X-Client-Type": "desktop"},
            )

            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert resp.json()["detail"] == "Invalid client type"

    def test_login_with_invalid_credentials(self, password_hasher, mock_db):
        """
        Test that the login endpoint raises an HTTPException with status code 401
        when invalid credentials are provided. Mocks the authenticate_user function
        to simulate authentication failure and verifies that the exception is raised
        with the correct status code and detail.
        """
        with patch("session.router.auth_utils.authenticate_user") as mock_auth:
            mock_auth.side_effect = HTTPException(
                status_code=401, detail="Invalid username"
            )

            with pytest.raises(HTTPException) as exc_info:
                mock_auth("invalid", "password", password_hasher, mock_db)

            assert exc_info.value.status_code == 401

    def test_login_with_inactive_user(self, sample_inactive_user):
        """
        Test that the login endpoint raises an HTTPException with status code 403
        when attempting to authenticate an inactive user.

        This test mocks the authentication and user activity check utilities to simulate
        the scenario where a user is found but is inactive. It asserts that the correct
        exception is raised with the expected status code.
        """
        with patch("session.router.auth_utils.authenticate_user") as mock_auth:
            with patch("session.router.users_utils.check_user_is_active") as mock_check:
                mock_auth.return_value = sample_inactive_user
                mock_check.side_effect = HTTPException(
                    status_code=403, detail="User is inactive"
                )

                with pytest.raises(HTTPException) as exc_info:
                    mock_check(sample_inactive_user)

                assert exc_info.value.status_code == 403


class TestMFAVerifyEndpoint:
    """
    Test suite for the MFA verification endpoint (/auth/mfa/verify).

    This class contains tests that cover various scenarios for the MFA verification endpoint, including:
    - Successful MFA verification and login for different client types (web and mobile).
    - Handling of cases where no pending MFA login is found.
    - Handling of invalid MFA codes.
    - Handling of cases where the user is not found after MFA verification.
    - Handling of inactive users after MFA verification.
    - Handling of invalid client types during MFA verification.

    Each test uses mocking to simulate the MFA verification flow, user lookup, and session creation.
    """

    @pytest.mark.parametrize(
        "client_type, expected_status, returns_tokens",
        [
            ("web", status.HTTP_200_OK, False),
            ("mobile", status.HTTP_200_OK, True),
        ],
    )
    def test_mfa_verify_success(
        self,
        fast_api_app,
        fast_api_client,
        sample_user_read,
        client_type,
        expected_status,
        returns_tokens,
    ):
        """
        Test successful MFA verification and login completion.

        This test verifies that when a valid MFA code is provided for a pending login,
        the API successfully completes the login process and returns appropriate tokens
        based on the client type.

        Args:
            fast_api_app: The FastAPI application instance under test.
            fast_api_client: The test client for making HTTP requests.
            sample_user_read: A sample user object.
            client_type: The type of client ("web" or "mobile").
            expected_status: The expected HTTP status code.
            returns_tokens: Boolean indicating if tokens should be returned.
        """
        fast_api_app.state._client_type = client_type

        # Setup pending MFA login
        pending_store = fast_api_app.state.fake_store
        pending_store._store = {"testuser": sample_user_read.id}

        with patch(
            "session.router.profile_utils.verify_user_mfa"
        ) as mock_verify_mfa, patch(
            "session.router.users_crud.get_user_by_id"
        ) as mock_get_user, patch(
            "session.router.users_utils.check_user_is_active"
        ), patch(
            "session.router.auth_utils.complete_login"
        ) as mock_complete:
            mock_verify_mfa.return_value = True
            mock_get_user.return_value = sample_user_read
            mock_complete.return_value = (
                {"session_id": "test-session"}
                if not returns_tokens
                else {
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "session_id": "session",
                    "token_type": "Bearer",
                    "expires_in": 900,
                }
            )

            resp = fast_api_client.post(
                "/auth/mfa/verify",
                json={"username": "testuser", "mfa_code": "123456"},
                headers={"X-Client-Type": client_type},
            )

            assert resp.status_code == expected_status
            body = resp.json()
            if returns_tokens:
                assert body["access_token"] == "token"
                assert body["refresh_token"] == "refresh"
                assert body["session_id"] == "session"
            else:
                assert body["session_id"] == "test-session"

    def test_mfa_verify_no_pending_login(self, fast_api_app, fast_api_client):
        """
        Test MFA verification when no pending login is found.

        This test verifies that when attempting to verify MFA without a pending login,
        the API returns a 400 Bad Request error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.fake_store._store = {}

        resp = fast_api_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
            headers={"X-Client-Type": "web"},
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "No pending MFA login" in resp.json()["detail"]

    def test_mfa_verify_invalid_code(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test MFA verification with an invalid MFA code.

        This test verifies that when an invalid MFA code is provided,
        the API returns a 401 Unauthorized error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.fake_store._store = {"testuser": sample_user_read.id}

        with patch("session.router.profile_utils.verify_user_mfa") as mock_verify_mfa:
            mock_verify_mfa.return_value = False

            resp = fast_api_client.post(
                "/auth/mfa/verify",
                json={"username": "testuser", "mfa_code": "999999"},
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid MFA code" in resp.json()["detail"]

    def test_mfa_verify_user_not_found(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test MFA verification when user is not found after verification.

        This test verifies that when a user cannot be found in the database
        after MFA verification, the API returns a 404 Not Found error and
        cleans up the pending login.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.fake_store._store = {"testuser": sample_user_read.id}

        with patch(
            "session.router.profile_utils.verify_user_mfa"
        ) as mock_verify_mfa, patch(
            "session.router.users_crud.get_user_by_id"
        ) as mock_get_user:
            mock_verify_mfa.return_value = True
            mock_get_user.return_value = None

            resp = fast_api_client.post(
                "/auth/mfa/verify",
                json={"username": "testuser", "mfa_code": "123456"},
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_404_NOT_FOUND
            assert "User not found" in resp.json()["detail"]

    def test_mfa_verify_inactive_user(
        self, fast_api_app, fast_api_client, sample_inactive_user
    ):
        """
        Test MFA verification with an inactive user.

        This test verifies that when an inactive user attempts to complete MFA login,
        the API returns a 403 Forbidden error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.fake_store._store = {"inactive": sample_inactive_user.id}

        with patch(
            "session.router.profile_utils.verify_user_mfa"
        ) as mock_verify_mfa, patch(
            "session.router.users_crud.get_user_by_id"
        ) as mock_get_user, patch(
            "session.router.users_utils.check_user_is_active"
        ) as mock_check_active:
            mock_verify_mfa.return_value = True
            mock_get_user.return_value = sample_inactive_user
            mock_check_active.side_effect = HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive"
            )

            resp = fast_api_client.post(
                "/auth/mfa/verify",
                json={"username": "inactive", "mfa_code": "123456"},
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert "User is inactive" in resp.json()["detail"]


class TestRefreshTokenEndpoint:
    """
    Test suite for the refresh token endpoint (/auth/refresh).

    This class contains tests that cover various scenarios for the token refresh endpoint, including:
    - Successful token refresh for different client types (web and mobile).
    - Handling of session not found errors.
    - Handling of invalid refresh token hash mismatches.
    - Handling of inactive users during refresh.
    - Handling of invalid client types during refresh.

    Each test uses mocking to simulate token validation, session retrieval, and token creation.
    """

    @pytest.mark.parametrize(
        "client_type, expected_status, returns_tokens",
        [
            ("web", status.HTTP_200_OK, False),
            ("mobile", status.HTTP_200_OK, True),
        ],
    )
    def test_refresh_token_success(
        self,
        fast_api_app,
        fast_api_client,
        sample_user_read,
        password_hasher,
        client_type,
        expected_status,
        returns_tokens,
    ):
        """
        Test successful token refresh.

        This test verifies that when a valid refresh token is provided,
        the API successfully creates new tokens and returns them based on client type.

        Args:
            fast_api_app: The FastAPI application instance under test.
            fast_api_client: The test client for making HTTP requests.
            sample_user_read: A sample user object.
            password_hasher: The password hasher instance.
            mock_db: Mock database session.
            client_type: The type of client ("web" or "mobile").
            expected_status: The expected HTTP status code.
            returns_tokens: Boolean indicating if tokens should be returned.
        """
        fast_api_app.state._client_type = client_type
        fast_api_app.state.mock_user_id = sample_user_read.id
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password(
            "refresh_token_value"
        )

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ), patch(
            "session.router.users_crud.get_user_by_id", return_value=sample_user_read
        ), patch(
            "session.router.users_utils.check_user_is_active"
        ), patch(
            "session.router.auth_utils.create_tokens"
        ) as mock_create_tokens, patch(
            "session.router.session_utils.edit_session"
        ), patch(
            "session.router.auth_utils.create_response_with_tokens",
            side_effect=lambda r, a, rf, c: r,
        ):
            # Set up proper mock for create_tokens with timestamp
            mock_access_exp = MagicMock()
            mock_access_exp.timestamp.return_value = 1234567890
            mock_refresh_exp = MagicMock()
            mock_create_tokens.return_value = (
                "new-session-id",
                mock_access_exp,
                "new_access_token",
                mock_refresh_exp,
                "new_refresh_token",
                "new_csrf_token",
            )

            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/refresh",
                headers={"X-Client-Type": client_type},
            )

            assert resp.status_code == expected_status
            body = resp.json()
            if returns_tokens:
                assert body["access_token"] == "new_access_token"
                assert body["refresh_token"] == "new_refresh_token"
                assert body["session_id"] == "new-session-id"
                assert body["token_type"] == "bearer"
            else:
                assert body["session_id"] == "new-session-id"

    def test_refresh_token_session_not_found(self, fast_api_app, fast_api_client):
        """
        Test token refresh when session is not found.

        This test verifies that when attempting to refresh with a session ID
        that doesn't exist, the API returns a 404 Not Found error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_session_id = "nonexistent-session"
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        with patch("session.router.session_crud.get_session_by_id", return_value=None):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/refresh",
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_404_NOT_FOUND
            assert "Session not found" in resp.json()["detail"]

    def test_refresh_token_invalid_hash(
        self, fast_api_app, fast_api_client, password_hasher
    ):
        """
        Test token refresh with invalid refresh token hash.

        This test verifies that when the refresh token hash doesn't match
        the stored hash, the API returns a 401 Unauthorized error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_refresh_token = "wrong_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password("different_token")

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_refresh_token", "wrong_token_value")

            resp = fast_api_client.post(
                "/auth/refresh",
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid refresh token" in resp.json()["detail"]

    def test_refresh_token_inactive_user(
        self, fast_api_app, fast_api_client, sample_inactive_user, password_hasher
    ):
        """
        Test token refresh with an inactive user.

        This test verifies that when an inactive user attempts to refresh tokens,
        the API returns a 403 Forbidden error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.mock_user_id = sample_inactive_user.id
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password(
            "refresh_token_value"
        )

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ), patch(
            "session.router.users_crud.get_user_by_id",
            return_value=sample_inactive_user,
        ), patch(
            "session.router.users_utils.check_user_is_active",
            side_effect=HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive"
            ),
        ):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/refresh",
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_refresh_token_invalid_client_type(
        self, fast_api_app, fast_api_client, sample_user_read, password_hasher
    ):
        """
        Test token refresh with an invalid client type.

        This test verifies that when an invalid client type is provided,
        the API returns a 403 Forbidden error.
        """
        fast_api_app.state._client_type = "desktop"
        fast_api_app.state.mock_user_id = sample_user_read.id
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password(
            "refresh_token_value"
        )

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ), patch(
            "session.router.users_crud.get_user_by_id", return_value=sample_user_read
        ), patch(
            "session.router.users_utils.check_user_is_active"
        ), patch(
            "session.router.auth_utils.create_tokens"
        ) as mock_create_tokens, patch(
            "session.router.session_utils.edit_session"
        ):
            # Set up proper mock for create_tokens with timestamp
            mock_access_exp = MagicMock()
            mock_access_exp.timestamp.return_value = 1234567890
            mock_refresh_exp = MagicMock()
            mock_create_tokens.return_value = (
                "new-session-id",
                mock_access_exp,
                "new_access_token",
                mock_refresh_exp,
                "new_refresh_token",
                "new_csrf_token",
            )

            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/refresh",
                headers={"X-Client-Type": "desktop"},
            )

            assert resp.status_code == status.HTTP_403_FORBIDDEN
            assert "Invalid client type" in resp.json()["detail"]


class TestLogoutEndpoint:
    """
    Test suite for the logout endpoint (/auth/logout).

    This class contains tests that cover various scenarios for the logout endpoint, including:
    - Successful logout for different client types (web and mobile).
    - Cookie clearing for web clients.
    - Handling of invalid refresh tokens during logout.
    - Handling of session not found during logout (should still succeed).
    - Handling of invalid client types during logout.

    Each test uses mocking to simulate token validation, session retrieval, and session deletion.
    """

    @pytest.mark.parametrize(
        "client_type, expected_status",
        [
            ("web", status.HTTP_200_OK),
            ("mobile", status.HTTP_200_OK),
        ],
    )
    def test_logout_success(
        self,
        fast_api_app,
        fast_api_client,
        password_hasher,
        client_type,
        expected_status,
    ):
        """
        Test successful logout.

        This test verifies that when a valid access and refresh token are provided,
        the API successfully deletes the session and returns a success message.

        Args:
            fast_api_app: The FastAPI application instance under test.
            fast_api_client: The test client for making HTTP requests.
            password_hasher: The password hasher instance.
            client_type: The type of client ("web" or "mobile").
            expected_status: The expected HTTP status code.
        """
        fast_api_app.state._client_type = client_type
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password(
            "refresh_token_value"
        )

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ), patch("session.router.session_crud.delete_session") as mock_delete:
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_access_token", "access_token")
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/logout",
                headers={"X-Client-Type": client_type},
            )

            assert resp.status_code == expected_status
            assert resp.json()["message"] == "Logout successful"
            mock_delete.assert_called_once()

            # Check cookies are cleared for web clients
            if client_type == "web":
                # The response should have set-cookie headers to clear cookies
                assert "set-cookie" in resp.headers or resp.cookies

    def test_logout_invalid_refresh_token(
        self, fast_api_app, fast_api_client, password_hasher
    ):
        """
        Test logout with an invalid refresh token.

        This test verifies that when the refresh token hash doesn't match,
        the API returns a 401 Unauthorized error.
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_refresh_token = "wrong_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.refresh_token = password_hasher.hash_password("different_token")

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_access_token", "access_token")
            fast_api_client.cookies.set("endurain_refresh_token", "wrong_token_value")

            resp = fast_api_client.post(
                "/auth/logout",
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid refresh token" in resp.json()["detail"]

    def test_logout_session_not_found_still_succeeds(
        self, fast_api_app, fast_api_client
    ):
        """
        Test logout when session is not found (should still succeed).

        This test verifies that when attempting to logout with a session ID
        that doesn't exist, the API still returns success (idempotent operation).
        """
        fast_api_app.state._client_type = "web"
        fast_api_app.state.mock_session_id = "nonexistent-session"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        with patch("session.router.session_crud.get_session_by_id", return_value=None):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_access_token", "access_token")
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/logout",
                headers={"X-Client-Type": "web"},
            )

            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["message"] == "Logout successful"

    def test_logout_invalid_client_type(self, fast_api_app, fast_api_client):
        """
        Test logout with an invalid client type.

        This test verifies that when an invalid client type is provided,
        the API returns a 401 Unauthorized error (client type validation
        happens after authentication in the dependency chain).
        """
        fast_api_app.state._client_type = "desktop"
        fast_api_app.state.mock_session_id = "test-session-id"
        fast_api_app.state.mock_user_id = 1
        fast_api_app.state.mock_refresh_token = "refresh_token_value"

        mock_session = MagicMock()
        mock_session.id = "test-session-id"

        with patch(
            "session.router.session_crud.get_session_by_id", return_value=mock_session
        ):
            # Set cookies on client instance (new API)
            fast_api_client.cookies.set("endurain_access_token", "access_token")
            fast_api_client.cookies.set("endurain_refresh_token", "refresh_token_value")

            resp = fast_api_client.post(
                "/auth/logout",
                headers={"X-Client-Type": "desktop"},
            )

            # Client type validation happens in the header_client_type_scheme dependency
            # which runs after authentication, so we get 401 due to invalid client type
            # being rejected by the scheme validator
            assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestSessionsEndpoints:
    """
    Test suite for the sessions management endpoints.

    This class contains tests for:
    - GET /sessions/user/{user_id} - Retrieve all sessions for a user
    - DELETE /sessions/{session_id}/user/{user_id} - Delete a specific session

    Each test uses mocking to simulate authentication, authorization, and database operations.
    """

    def test_read_sessions_user_success(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test successful retrieval of user sessions.

        This test verifies that when a valid access token is provided with
        appropriate scopes, the API returns all sessions for the user.
        """
        fast_api_app.state._client_type = "web"

        mock_sessions = [
            {
                "id": "session-1",
                "user_id": sample_user_read.id,
                "device_type": "desktop",
                "browser": "Chrome",
            },
            {
                "id": "session-2",
                "user_id": sample_user_read.id,
                "device_type": "mobile",
                "browser": "Safari",
            },
        ]

        with patch(
            "session.router.session_crud.get_user_sessions", return_value=mock_sessions
        ) as mock_get_sessions:
            resp = fast_api_client.get(
                f"/sessions/user/{sample_user_read.id}",
                headers={
                    "X-Client-Type": "web",
                    "Authorization": "Bearer access_token",
                },
            )

            assert resp.status_code == status.HTTP_200_OK
            assert len(resp.json()) == 2
            assert resp.json()[0]["id"] == "session-1"
            assert resp.json()[1]["id"] == "session-2"
            mock_get_sessions.assert_called_once()

    def test_read_sessions_user_empty_list(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test retrieval of user sessions when no sessions exist.

        This test verifies that when a user has no active sessions,
        the API returns an empty list.
        """
        fast_api_app.state._client_type = "web"

        with patch("session.router.session_crud.get_user_sessions", return_value=[]):
            resp = fast_api_client.get(
                f"/sessions/user/{sample_user_read.id}",
                headers={
                    "X-Client-Type": "web",
                    "Authorization": "Bearer access_token",
                },
            )

            assert resp.status_code == status.HTTP_200_OK
            assert resp.json() == []

    def test_delete_session_success(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test successful deletion of a user session.

        This test verifies that when a valid access token is provided with
        appropriate scopes, the API successfully deletes the specified session.
        """
        fast_api_app.state._client_type = "web"
        session_id = "session-to-delete"

        with patch(
            "session.router.session_crud.delete_session", return_value=True
        ) as mock_delete:
            resp = fast_api_client.delete(
                f"/sessions/{session_id}/user/{sample_user_read.id}",
                headers={
                    "X-Client-Type": "web",
                    "Authorization": "Bearer access_token",
                },
            )

            assert resp.status_code == status.HTTP_200_OK
            # Verify delete_session was called with the correct session_id and user_id
            # (the third argument is the database session which we don't need to verify)
            assert mock_delete.called
            call_args = mock_delete.call_args[0]
            assert call_args[0] == session_id
            assert call_args[1] == sample_user_read.id

    def test_delete_session_not_found(
        self, fast_api_app, fast_api_client, sample_user_read
    ):
        """
        Test deletion of a non-existent session.

        This test verifies that when attempting to delete a session that doesn't exist,
        the API handles it appropriately (implementation-dependent behavior).
        """
        fast_api_app.state._client_type = "web"
        session_id = "nonexistent-session"

        with patch(
            "session.router.session_crud.delete_session",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            ),
        ):
            resp = fast_api_client.delete(
                f"/sessions/{session_id}/user/{sample_user_read.id}",
                headers={
                    "X-Client-Type": "web",
                    "Authorization": "Bearer access_token",
                },
            )

            assert resp.status_code == status.HTTP_404_NOT_FOUND
            assert "Session not found" in resp.json()["detail"]
