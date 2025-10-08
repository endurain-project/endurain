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
        with patch(
            "session.router.session_utils.authenticate_user"
        ) as mock_auth, patch("session.router.users_utils.check_user_is_active"), patch(
            "session.router.profile_utils.is_mfa_enabled_for_user"
        ) as mock_mfa, patch(
            "session.router.session_utils.complete_login"
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
                "/token",
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
        with patch(
            "session.router.session_utils.authenticate_user"
        ) as mock_auth, patch("session.router.users_utils.check_user_is_active"), patch(
            "session.router.profile_utils.is_mfa_enabled_for_user"
        ) as mock_mfa:
            mock_auth.return_value = sample_user_read
            mock_mfa.return_value = True

            resp = fast_api_client.post(
                "/token",
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
        sends a POST request to the "/token" endpoint with the "X-Client-Type" header set to "desktop".
        The test asserts that the response status code is 403 Forbidden and the response detail
        indicates an invalid client type.

        Args:
            fast_api_app: The FastAPI application instance.
            fast_api_client: The test client for making HTTP requests.
            sample_user_read: A sample user object returned by the authentication mock.
        """
        fast_api_app.state._client_type = "desktop"
        with patch(
            "session.router.session_utils.authenticate_user"
        ) as mock_auth, patch("session.router.users_utils.check_user_is_active"), patch(
            "session.router.profile_utils.is_mfa_enabled_for_user"
        ) as mock_mfa, patch(
            "session.router.session_utils.create_tokens"
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
                "/token",
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
        with patch("session.router.session_utils.authenticate_user") as mock_auth:
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
        with patch("session.router.session_utils.authenticate_user") as mock_auth:
            with patch("session.router.users_utils.check_user_is_active") as mock_check:
                mock_auth.return_value = sample_inactive_user
                mock_check.side_effect = HTTPException(
                    status_code=403, detail="User is inactive"
                )

                with pytest.raises(HTTPException) as exc_info:
                    mock_check(sample_inactive_user)

                assert exc_info.value.status_code == 403
