"""Integration tests for password_reset_tokens API endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, status


class TestRequestPasswordReset:
    """
    Test suite for POST /password-reset/request endpoint.

    Verifies that the endpoint always responds with a
    generic 200 message to prevent user enumeration, and
    returns a 422 on malformed input.
    """

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.send_password_reset_email",
        new_callable=AsyncMock,
    )
    def test_request_password_reset_success(
        self,
        mock_send: AsyncMock,
        fast_api_client,
    ) -> None:
        """Returns 200 with a generic message when email is sent."""
        mock_send.return_value = True

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "user@example.com"},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "message" in body
        assert "password reset link" in body["message"]

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.send_password_reset_email",
        new_callable=AsyncMock,
    )
    def test_request_password_reset_send_fails(
        self,
        mock_send: AsyncMock,
        fast_api_client,
    ) -> None:
        """Returns 500 when the underlying email send fails."""
        mock_send.return_value = False

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "user@example.com"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_request_password_reset_invalid_email_format(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when the email field is not a valid address."""
        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "not-an-email"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_request_password_reset_missing_email(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when the email field is absent from the body."""
        response = fast_api_client.post(
            "/password-reset/request",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.send_password_reset_email",
        new_callable=AsyncMock,
    )
    def test_request_propagates_503_when_email_not_configured(
        self,
        mock_send: AsyncMock,
        fast_api_client,
    ) -> None:
        """
        Returns 503 when send_password_reset_email raises
        HTTPException 503 because email service is not configured.
        """
        mock_send.side_effect = HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "user@example.com"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.send_password_reset_email",
        new_callable=AsyncMock,
    )
    def test_request_returns_same_200_for_unknown_email(
        self,
        mock_send: AsyncMock,
        fast_api_client,
    ) -> None:
        """
        Returns 200 with the same generic message for an unknown
        email address, preventing user enumeration.

        The send_password_reset_email utility returns True for
        unknown emails without sending anything; the router must
        not reveal whether the address is registered.
        """
        # Simulate the anti-enumeration behaviour from utils:
        # returns True even when user is not found.
        mock_send.return_value = True

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "doesnotexist@example.com"},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "message" in body
        # Response must be indistinguishable from a successful send
        assert "password reset link" in body["message"]


class TestConfirmPasswordReset:
    """
    Test suite for POST /password-reset/confirm endpoint.

    Verifies successful password reset, rejection of
    invalid or expired tokens, and validation errors for
    passwords that are too short.
    """

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.use_password_reset_token",
    )
    def test_confirm_password_reset_success(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Returns 200 with success message on a valid token."""
        mock_use.return_value = None

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "valid-reset-token-value",
                "new_password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Password reset successful"

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.use_password_reset_token",
    )
    def test_confirm_password_reset_invalid_token(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Returns 400 when the token is invalid or expired."""
        mock_use.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "expired-or-invalid-token",
                "new_password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.use_password_reset_token",
    )
    def test_confirm_password_reset_policy_violation(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Returns 422 (distinct from the 400 invalid-token case) when the new
        password fails the account's configured password policy (e.g. a
        length/complexity requirement above the schema's own 8-char floor)."""
        mock_use.side_effect = HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Password is too short (got 8, need \u2265 12).",
        )

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "valid-reset-token-value",
                "new_password": "8-chars!",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_confirm_password_reset_password_too_short(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when new_password is shorter than 8 chars."""
        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "some-token-value",
                "new_password": "short",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_confirm_password_reset_missing_token(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when the token field is absent from the body."""
        response = fast_api_client.post(
            "/password-reset/confirm",
            json={"new_password": "new-secure-pass"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch(
        "modules.auth.password_reset_tokens.router.password_reset_tokens_utils.use_password_reset_token",
    )
    def test_confirm_propagates_500_from_use_password_reset_token(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """
        Returns 500 when use_password_reset_token raises
        HTTPException 500 (e.g. database write fails after claim).
        """
        mock_use.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "some-valid-token",
                "new_password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
