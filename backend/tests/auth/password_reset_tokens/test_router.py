"""Integration tests for password_reset_tokens API endpoints."""

from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status

import modules.auth.credentials.contracts as credentials_contracts


class TestRequestPasswordReset:
    """
    Test suite for POST /password-reset/request endpoint.

    Verifies that the endpoint always responds with a
    generic 200 message to prevent user enumeration, and
    returns a 422 on malformed input.
    """

    @patch("modules.auth.password_reset_tokens.public_router.password_reset_service.request_password_reset_email")
    def test_request_password_reset_success(
        self,
        mock_send: MagicMock,
        fast_api_client,
    ) -> None:
        """Returns 204 with no body once the email is queued."""

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "user@example.com"},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    @patch("modules.auth.password_reset_tokens.public_router.core_network.get_ip_address", return_value="203.0.113.7")
    @patch("modules.auth.password_reset_tokens.public_router.password_reset_service.request_password_reset_email")
    def test_request_passes_the_clients_address_and_user_agent(
        self, mock_send: MagicMock, _ip: MagicMock, fast_api_client
    ) -> None:
        """Hands the service the caller's network address and user agent for the worker's audit rows."""
        fast_api_client.post(
            "/password-reset/request", json={"email": "user@example.com"}, headers={"User-Agent": "reset-agent/1.0"}
        )

        email, ip_address, user_agent, _db = mock_send.call_args.args
        assert email == "user@example.com"
        assert ip_address == "203.0.113.7"
        assert user_agent == "reset-agent/1.0"

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

    @patch("modules.auth.password_reset_tokens.public_router.password_reset_service.request_password_reset_email")
    def test_request_propagates_503_when_email_not_configured(
        self,
        mock_send: MagicMock,
        fast_api_client,
    ) -> None:
        """
        Returns 503 when request_password_reset_email raises
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

    @patch("modules.auth.password_reset_tokens.public_router.password_reset_service.request_password_reset_email")
    def test_request_returns_same_204_for_unknown_email(
        self,
        mock_send: MagicMock,
        fast_api_client,
    ) -> None:
        """
        Returns the same 204 with no body for an unknown
        email address, preventing user enumeration.

        The request_password_reset_email utility returns quietly for
        unknown emails without queueing anything; the router must
        not reveal whether the address is registered.
        """

        response = fast_api_client.post(
            "/password-reset/request",
            json={"email": "doesnotexist@example.com"},
        )

        # Response must be indistinguishable from a successful send
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""


class TestConfirmPasswordReset:
    """
    Test suite for POST /password-reset/confirm endpoint.

    Verifies successful password reset, rejection of
    invalid or expired tokens, and validation errors for
    passwords that are too short.
    """

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
    )
    def test_confirm_password_reset_success(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Returns 204 with no body on a valid token."""
        mock_use.return_value = None

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "valid-reset-token-value",
                "password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
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
                "password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
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
                "password": "8-chars!",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
    )
    def test_confirm_password_reset_password_too_short(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Hands a password under 8 characters to the service, whose policy check answers a typed error."""
        mock_use.return_value = None

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={
                "token": "some-token-value",
                "password": "short",
            },
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert mock_use.call_args.args[:2] == ("some-token-value", "short")

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
    )
    def test_confirm_password_reset_answers_the_typed_password_too_short_problem(
        self,
        mock_use,
        fast_api_client,
    ) -> None:
        """Answers 422 with the ``password-too-short`` problem type through the real domain-error handler."""
        mock_use.side_effect = credentials_contracts.PasswordTooShortError("short")

        response = fast_api_client.post(
            "/password-reset/confirm",
            json={"token": "some-token-value", "password": "short"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["type"] == "urn:endurain:error:password-too-short"

    def test_confirm_password_reset_refuses_the_old_new_password_key(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when the body still uses the retired new_password key."""
        response = fast_api_client.post(
            "/password-reset/confirm",
            json={"token": "some-token-value", "new_password": "new-secure-pass"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_confirm_password_reset_missing_token(
        self,
        fast_api_client,
    ) -> None:
        """Returns 422 when the token field is absent from the body."""
        response = fast_api_client.post(
            "/password-reset/confirm",
            json={"password": "new-secure-pass"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch(
        "modules.auth.password_reset_tokens.public_router.password_reset_service.use_password_reset_token",
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
                "password": "new-secure-pass",
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestValidatePasswordResetToken:
    """Test suite for POST /password-reset/validate endpoint."""

    @patch("modules.auth.password_reset_tokens.public_router.password_reset_service.validate_password_reset_token")
    def test_validate_returns_204_without_body(self, mock_validate, fast_api_client) -> None:
        """Returns 204 with an empty body when the token is usable."""
        response = fast_api_client.post("/password-reset/validate", json={"token": "valid-reset-token-value"})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        assert mock_validate.call_args.args[0] == "valid-reset-token-value"

    def test_validate_missing_token(self, fast_api_client) -> None:
        """Returns 422 when the token field is absent."""
        assert fast_api_client.post("/password-reset/validate", json={}).status_code == (
            status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    def test_validate_rejects_extra_fields(self, fast_api_client) -> None:
        """Returns 422 when the body carries anything but the token."""
        response = fast_api_client.post("/password-reset/validate", json={"token": "t", "new_password": "x" * 12})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
