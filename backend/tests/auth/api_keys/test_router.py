"""Tests for users_api_keys API endpoints."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status

import modules.auth.api_keys.models as users_api_keys_models
import modules.auth.identity_service as auth_identity_service


class TestGetUserApiKeys:
    """
    Test suite for GET /api_keys endpoint.
    """

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.get_api_keys_by_user_id")
    def test_get_user_api_keys_success(self, mock_get_keys, fast_api_client, fast_api_app):
        """Test successful retrieval of all API keys returns 200 with a list."""
        # Arrange
        now = datetime.now(UTC)
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key.id = "some-uuid"
        mock_key.user_id = 1
        mock_key.name = "FitoTrack"
        mock_key.key_prefix = "abcdefgh"
        mock_key.scopes = '["activities:upload"]'
        mock_key.expires_at = None
        mock_key.last_used_at = None
        mock_key.created_at = now
        mock_key.is_active = True
        mock_get_keys.return_value = [mock_key]

        # Act
        response = fast_api_client.get(
            "/api_keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.get_api_keys_by_user_id")
    def test_get_user_api_keys_empty(self, mock_get_keys, fast_api_client, fast_api_app):
        """Test that an empty list is returned when the user has no API keys."""
        # Arrange
        mock_get_keys.return_value = []

        # Act
        response = fast_api_client.get(
            "/api_keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json() == []


class TestCreateUserApiKey:
    """
    Test suite for POST /api_keys endpoint.
    """

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.api_keys_utils.validate_api_key_scopes")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_success(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_validate_scopes,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful API key creation returns 201 with the key in the response."""
        # Arrange
        now = datetime.now(UTC)
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user

        mock_verify_step_up.return_value = None
        mock_validate_scopes.return_value = None

        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = "new-uuid"
        mock_orm_key.user_id = 1
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = None
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = (mock_orm_key, "endurain_rawsecretkey")

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        # Act
        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        assert data["key"] == "endurain_rawsecretkey"

    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_user_not_found_returns_404(self, mock_get_user, fast_api_client, fast_api_app):
        """Test that 404 is returned when the authenticated user is not found."""
        # Arrange
        mock_get_user.return_value = None

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        # Act
        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404

    @patch("modules.auth.api_keys.router.api_keys_utils.validate_api_key_scopes")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_scope_exceeds_permission_returns_400(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_validate_scopes,
        fast_api_client,
        fast_api_app,
    ):
        """Test that 400 is returned when requested scopes exceed the user's own permissions."""
        # Arrange
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.return_value = None
        mock_validate_scopes.side_effect = ValueError(
            "Unsupported API key scopes: {'users:write'}. Valid scopes: {'activities:upload'}"
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        # Act
        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 400

    def test_create_user_api_key_invalid_scope_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned for an unknown scope (Pydantic validation failure)."""
        # Arrange: schema validator rejects unsupported scopes first
        payload = {
            "name": "FitoTrack",
            "scopes": ["fake:scope_that_does_not_exist"],
        }

        # Act
        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 422

    def test_create_user_api_key_empty_name_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned when the name is empty (min_length violation)."""
        payload = {
            "name": "",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_create_user_api_key_empty_scopes_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned when the scopes list is empty."""
        payload = {
            "name": "FitoTrack",
            "scopes": [],
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_missing_password_returns_401(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Step-up with missing password propagates 401.

        When the account has a local password and none is
        supplied, verify_step_up_credentials raises 401
        and create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 401
        mock_create.assert_not_called()

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_wrong_password_returns_401(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Step-up with wrong password propagates 401.

        When the caller supplies an incorrect password,
        verify_step_up_credentials raises 401 and
        create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "current_password": "definitely_wrong",
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 401
        mock_create.assert_not_called()

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_mfa_missing_code_returns_401(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        MFA required but no code supplied propagates 401.

        When MFA is enabled and mfa_code is absent,
        verify_step_up_credentials raises 401 and
        create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "current_password": "correct_password",
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 401
        mock_create.assert_not_called()

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_user_api_key_mfa_invalid_code_returns_401(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        MFA with invalid code propagates 401.

        When MFA is enabled and an incorrect mfa_code is
        supplied, verify_step_up_credentials raises 401
        and create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "current_password": "correct_password",
            "mfa_code": "000000",
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 401
        mock_create.assert_not_called()

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_step_up_failure_does_not_call_create_api_key(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        When step-up fails, create_api_key is never called.

        Asserts the database write is skipped entirely on
        any step-up 401.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "Unwanted Key",
            "scopes": ["activities:upload"],
            "current_password": "bad",
        }

        fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        mock_create.assert_not_called()

    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_create_passes_password_and_mfa_code_to_step_up(
        self,
        mock_get_user,
        mock_verify_step_up,
        fast_api_client,
        fast_api_app,
    ):
        """
        Password and mfa_code from schema are forwarded to
        verify_step_up_credentials.

        Validates that step-up receives the exact values the
        caller placed in the request body.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_identity_service = MagicMock()
        fast_api_app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        # Cause a controlled 401 so we can inspect the call
        mock_verify_step_up.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up verification failed",
        )

        payload = {
            "name": "MyKey",
            "scopes": ["activities:upload"],
            "current_password": "s3cr3t!",
            "mfa_code": "123456",
        }

        fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        mock_verify_step_up.assert_called_once()
        _call_kwargs = mock_verify_step_up.call_args
        positional = _call_kwargs.args
        # verify_step_up_credentials(user_id, password, mfa, …)
        assert positional[1] == "s3cr3t!"
        assert positional[2] == "123456"
        assert positional[3] is mock_identity_service


class TestApiKeyResponseSafety:
    """
    Response schema safety tests for API key endpoints.

    Ensures raw key material and internal hashes never
    appear in list or single-key responses, and that the
    raw key is returned exactly once in the creation
    response.
    """

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.get_api_keys_by_user_id")
    def test_list_response_excludes_key_and_key_hash(
        self,
        mock_get_keys,
        fast_api_client,
        fast_api_app,
    ):
        """
        List response must not leak raw key or key_hash.

        Even if the ORM model carries key_hash, the
        UsersApiKeyRead schema must exclude it.
        """
        now = datetime.now(UTC)
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key.id = "some-uuid"
        mock_key.user_id = 1
        mock_key.name = "FitoTrack"
        mock_key.key_prefix = "abcdefgh"
        mock_key.key_hash = "deadbeef" * 8  # ORM has it
        mock_key.scopes = '["activities:upload"]'
        mock_key.expires_at = None
        mock_key.last_used_at = None
        mock_key.created_at = now
        mock_key.is_active = True
        mock_get_keys.return_value = [mock_key]

        response = fast_api_client.get(
            "/api_keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        assert "key" not in item, "Raw key must not appear in list response"
        assert "key_hash" not in item, "key_hash must not appear in list response"

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.api_keys_utils.validate_api_key_scopes")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_created_response_includes_raw_key_once(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_validate_scopes,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Creation response includes the raw key exactly once.

        The key must be in the top-level response body and
        must not be duplicated under any other field name.
        """
        now = datetime.now(UTC)
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.return_value = None
        mock_validate_scopes.return_value = None

        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = "new-uuid"
        mock_orm_key.user_id = 1
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.key_hash = "deadbeef" * 8
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = None
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = (
            mock_orm_key,
            "endurain_rawsecretkey",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data.get("key") == "endurain_rawsecretkey", "Raw key must appear in creation response"
        # Count occurrences across all values, not just keys
        raw_key_occurrences = sum(1 for v in data.values() if v == "endurain_rawsecretkey")
        assert raw_key_occurrences == 1, "Raw key must appear exactly once"

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.create_api_key")
    @patch("modules.auth.api_keys.router.api_keys_utils.validate_api_key_scopes")
    @patch("modules.auth.api_keys.router.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.api_keys.router.users_crud.get_user_by_id")
    def test_created_response_excludes_key_hash(
        self,
        mock_get_user,
        mock_verify_step_up,
        mock_validate_scopes,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Creation response must not expose key_hash.

        The ORM model stores key_hash but the response
        schema must never include it.
        """
        now = datetime.now(UTC)
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.return_value = None
        mock_validate_scopes.return_value = None

        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = "new-uuid"
        mock_orm_key.user_id = 1
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.key_hash = "deadbeef" * 8
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = None
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = (
            mock_orm_key,
            "endurain_rawsecretkey",
        )

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api_keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "key_hash" not in data, "key_hash must never appear in API response"


class TestRevokeUserApiKey:
    """
    Test suite for PATCH /api_keys/{api_key_id}/revoke endpoint.
    """

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.revoke_api_key")
    def test_revoke_user_api_key_success(self, mock_revoke, fast_api_client, fast_api_app):
        """Test successful key revocation returns 204 No Content."""
        # Arrange
        mock_revoke.return_value = None

        # Act
        response = fast_api_client.patch(
            "/api_keys/some-uuid/revoke",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.revoke_api_key")
    def test_revoke_user_api_key_not_found_returns_404(self, mock_revoke, fast_api_client, fast_api_app):
        """Test that 404 is returned when the key is not found or belongs to another user."""
        # Arrange
        mock_revoke.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found for user",
        )

        # Act
        response = fast_api_client.patch(
            "/api_keys/nonexistent-uuid/revoke",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteUserApiKey:
    """
    Test suite for DELETE /api_keys/{api_key_id} endpoint.
    """

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.delete_api_key")
    def test_delete_user_api_key_success(self, mock_delete, fast_api_client, fast_api_app):
        """Test successful key deletion returns 204 No Content."""
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/api_keys/some-uuid",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.auth.api_keys.router.auth_api_keys_crud.delete_api_key")
    def test_delete_user_api_key_not_found_returns_404(self, mock_delete, fast_api_client, fast_api_app):
        """Test that 404 is returned when the key does not exist."""
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found for user",
        )

        # Act
        response = fast_api_client.delete(
            "/api_keys/nonexistent-uuid",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
