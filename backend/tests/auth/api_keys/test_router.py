"""Tests for users_api_keys API endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

import core.exceptions as core_exceptions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as users_api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
from tests._helpers.auth import MOCK_USER_ID

KEY_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
MISSING_KEY_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
NEW_KEY_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a3")


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    with patch(
        "modules.auth.account_security.dependencies.server_settings_integration.get_session_policy",
        return_value=session_policy,
    ):
        yield


class TestGetUserApiKeys:
    """
    Test suite for GET /api-keys endpoint.
    """

    @patch("modules.auth.account_security.api_keys_router.api_key_service.list_user_api_keys")
    def test_list_user_api_keys_success(self, mock_get_keys, fast_api_client, fast_api_app):
        """Test successful retrieval of all API keys returns 200 with a list."""
        # Arrange
        now = datetime.now(UTC)
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key.id = KEY_ID
        mock_key.user_id = MOCK_USER_ID
        mock_key.name = "FitoTrack"
        mock_key.key_prefix = "abcdefgh"
        mock_key.scopes = '["activities:upload"]'
        mock_key.expires_at = now + timedelta(days=30)
        mock_key.last_used_at = None
        mock_key.created_at = now
        mock_key.is_active = True
        mock_get_keys.return_value = api_keys_schema.UserApiKeyPage.build(
            [api_keys_schema.UserApiKeyRead.model_validate(mock_key)], 1, 1, 25
        )

        # Act
        response = fast_api_client.get(
            "/api-keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["scopes"] == ["activities:upload"]

    @patch("modules.auth.account_security.api_keys_router.api_key_service.list_user_api_keys")
    def test_list_user_api_keys_empty(self, mock_get_keys, fast_api_client, fast_api_app):
        """Test that an empty list is returned when the user has no API keys."""
        # Arrange
        mock_get_keys.return_value = api_keys_schema.UserApiKeyPage.build([], 0, 1, 25)

        # Act
        response = fast_api_client.get(
            "/api-keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0


class TestCreateUserApiKey:
    """
    Test suite for POST /api_keys endpoint.
    """

    @pytest.fixture(autouse=True)
    def below_the_key_limit(self):
        """Count no active keys so a create reaches the step-up and the key insert."""
        with patch("modules.auth.account_security.api_key_service.api_keys_integration.count_active_api_keys") as count:
            count.return_value = 0
            yield count

    def test_create_user_api_key_at_the_limit_returns_409(self, below_the_key_limit, fast_api_client, fast_api_app):
        """Test that 409 with the api-key-limit problem type is returned at the cap."""
        below_the_key_limit.return_value = api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER

        response = fast_api_client.post(
            "/api-keys",
            json={"step_up": {"current_password": "pw"}, "name": "FitoTrack", "scopes": ["activities:upload"]},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:api-key-limit"

    @patch("modules.auth.account_security.api_key_service.create_user_api_key")
    def test_create_user_api_key_success(
        self,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful API key creation returns 201 with the key in the response."""
        # Arrange
        now = datetime.now(UTC)
        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = NEW_KEY_ID
        mock_orm_key.user_id = MOCK_USER_ID
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = now + timedelta(days=30)
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = api_keys_schema.UserApiKeyCreatedRead(
            id=mock_orm_key.id,
            user_id=MOCK_USER_ID,
            name=mock_orm_key.name,
            key_prefix=mock_orm_key.key_prefix,
            scopes=mock_orm_key.scopes,
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
            key="endurain_rawsecretkey",
        )

        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        # Act
        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        assert data["key"] == "endurain_rawsecretkey"
        assert data["scopes"] == ["activities:upload"]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_create_user_api_key_user_not_found_returns_404(
        self, mock_get_user, fast_api_client, fast_api_app, mock_db
    ):
        """Test that 404 is returned when the authenticated user is not found."""
        # Arrange
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.scalar_one.return_value = 0

        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        # Act
        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404

    def test_create_user_api_key_past_expiry_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned for an expiry that has already passed."""
        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "expires_at": "2020-01-01",
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_create_user_api_key_expiry_beyond_the_maximum_returns_422_on_expires_at(
        self, fast_api_client, fast_api_app
    ):
        """An expiry later than the maximum API key lifetime is a field error on expires_at."""
        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "expires_at": (datetime.now(UTC) + timedelta(days=366)).isoformat(),
        }

        response = fast_api_client.post("/api-keys", json=payload, headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "body.expires_at"

    def test_create_user_api_key_invalid_scope_message_has_no_set_repr(self, fast_api_client, fast_api_app):
        """Test that the 422 body names the scopes without a Python set repr."""
        payload = {"step_up": {"current_password": "pw"}, "name": "FitoTrack", "scopes": ["bogus:scope"]}

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422
        assert "activities:upload" in response.text
        assert "frozenset" not in response.text

    def test_create_user_api_key_invalid_scope_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned for an unknown scope (Pydantic validation failure)."""
        # Arrange: schema validator rejects unsupported scopes first
        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["fake:scope_that_does_not_exist"],
        }

        # Act
        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 422

    def test_create_user_api_key_empty_name_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned when the name is empty (min_length violation)."""
        payload = {
            "step_up": {"current_password": "pw"},
            "name": "",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    def test_create_user_api_key_empty_scopes_returns_422(self, fast_api_client, fast_api_app):
        """Test that 422 is returned when the scopes list is empty."""
        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": [],
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.api_keys_integration.create_api_key")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_create_user_api_key_missing_password_returns_403(
        self,
        mock_get_user,
        mock_create_api_key,
        mock_verify_step_up,
        fast_api_client,
        fast_api_app,
    ):
        """
        Step-up with missing password propagates 401.

        When the account has a local password and none is
        supplied, verify_step_up_credentials raises 403
        and create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 403
        mock_create_api_key.assert_not_called()

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.api_keys_integration.create_api_key")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_create_user_api_key_wrong_password_returns_403(
        self,
        mock_get_user,
        mock_create_api_key,
        mock_verify_step_up,
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
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "step_up": {"current_password": "definitely_wrong"},
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 403
        mock_create_api_key.assert_not_called()

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.api_keys_integration.create_api_key")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_create_user_api_key_mfa_missing_code_returns_403(
        self,
        mock_get_user,
        mock_create_api_key,
        mock_verify_step_up,
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
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "step_up": {"current_password": "correct_password"},
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 403
        mock_create_api_key.assert_not_called()

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.api_keys_integration.create_api_key")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_create_user_api_key_mfa_invalid_code_returns_403(
        self,
        mock_get_user,
        mock_create_api_key,
        mock_verify_step_up,
        fast_api_client,
        fast_api_app,
    ):
        """
        MFA with invalid code propagates 401.

        When MFA is enabled and an incorrect mfa_code is
        supplied, verify_step_up_credentials raises 403
        and create_api_key must not be called.
        """
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_get_user.return_value = mock_user
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
            "step_up": {"current_password": "correct_password", "mfa_code": "000000"},
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 403
        mock_create_api_key.assert_not_called()

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.api_keys_integration.create_api_key")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
    def test_step_up_failure_does_not_call_create_api_key(
        self,
        mock_get_user,
        mock_create_api_key,
        mock_verify_step_up,
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
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "name": "Unwanted Key",
            "scopes": ["activities:upload"],
            "step_up": {"current_password": "bad"},
        }

        fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        mock_create_api_key.assert_not_called()

    @patch("modules.auth.account_security.api_key_service.step_up_service.verify_step_up_credentials")
    @patch("modules.auth.account_security.api_key_service.users_integration.require_user")
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
        # Cause a controlled refusal so we can inspect the call
        mock_verify_step_up.side_effect = core_exceptions.StepUpFailedError()

        payload = {
            "name": "MyKey",
            "scopes": ["activities:upload"],
            "step_up": {"current_password": "s3cr3t!", "mfa_code": "123456"},
        }

        fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        mock_verify_step_up.assert_called_once()
        _call_kwargs = mock_verify_step_up.call_args
        positional = _call_kwargs.args
        # verify_step_up_credentials(user_id, password, mfa, …)
        assert positional[1] == "s3cr3t!"
        assert positional[2] == "123456"
        assert positional[3] is not None


class TestApiKeyResponseSafety:
    """
    Response schema safety tests for API key endpoints.

    Ensures raw key material and internal hashes never
    appear in list or single-key responses, and that the
    raw key is returned exactly once in the creation
    response.
    """

    @patch("modules.auth.account_security.api_keys_router.api_key_service.list_user_api_keys")
    def test_list_response_excludes_key_and_key_hash(
        self,
        mock_get_keys,
        fast_api_client,
        fast_api_app,
    ):
        """
        List response must not leak raw key or key_hash.

        Even if the ORM model carries key_hash, the
        UserApiKeyRead schema must exclude it.
        """
        now = datetime.now(UTC)
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key.id = KEY_ID
        mock_key.user_id = MOCK_USER_ID
        mock_key.name = "FitoTrack"
        mock_key.key_prefix = "abcdefgh"
        mock_key.key_hash = "deadbeef" * 8  # ORM has it
        mock_key.scopes = '["activities:upload"]'
        mock_key.expires_at = now + timedelta(days=30)
        mock_key.last_used_at = None
        mock_key.created_at = now
        mock_key.is_active = True
        mock_get_keys.return_value = api_keys_schema.UserApiKeyPage.build(
            [api_keys_schema.UserApiKeyRead.model_validate(mock_key)], 1, 1, 25
        )

        response = fast_api_client.get(
            "/api-keys",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "key" not in item, "Raw key must not appear in list response"
        assert "key_hash" not in item, "key_hash must not appear in list response"

    @patch("modules.auth.account_security.api_key_service.create_user_api_key")
    def test_created_response_includes_raw_key_once(
        self,
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
        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = NEW_KEY_ID
        mock_orm_key.user_id = MOCK_USER_ID
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.key_hash = "deadbeef" * 8
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = now + timedelta(days=30)
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = api_keys_schema.UserApiKeyCreatedRead(
            id=mock_orm_key.id,
            user_id=MOCK_USER_ID,
            name=mock_orm_key.name,
            key_prefix=mock_orm_key.key_prefix,
            scopes=mock_orm_key.scopes,
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
            key="endurain_rawsecretkey",
        )

        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data.get("key") == "endurain_rawsecretkey", "Raw key must appear in creation response"
        # Count occurrences across all values, not just keys
        raw_key_occurrences = sum(1 for v in data.values() if v == "endurain_rawsecretkey")
        assert raw_key_occurrences == 1, "Raw key must appear exactly once"

    @patch("modules.auth.account_security.api_key_service.create_user_api_key")
    def test_created_response_excludes_key_hash(
        self,
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
        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_orm_key.id = NEW_KEY_ID
        mock_orm_key.user_id = MOCK_USER_ID
        mock_orm_key.name = "FitoTrack"
        mock_orm_key.key_prefix = "abcdefgh"
        mock_orm_key.key_hash = "deadbeef" * 8
        mock_orm_key.scopes = '["activities:upload"]'
        mock_orm_key.expires_at = now + timedelta(days=30)
        mock_orm_key.last_used_at = None
        mock_orm_key.created_at = now
        mock_orm_key.is_active = True
        mock_create.return_value = api_keys_schema.UserApiKeyCreatedRead(
            id=mock_orm_key.id,
            user_id=MOCK_USER_ID,
            name=mock_orm_key.name,
            key_prefix=mock_orm_key.key_prefix,
            scopes=mock_orm_key.scopes,
            expires_at=now + timedelta(days=30),
            last_used_at=None,
            created_at=now,
            is_active=True,
            key="endurain_rawsecretkey",
        )

        payload = {
            "step_up": {"current_password": "pw"},
            "name": "FitoTrack",
            "scopes": ["activities:upload"],
        }

        response = fast_api_client.post(
            "/api-keys",
            json=payload,
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "key_hash" not in data, "key_hash must never appear in API response"


class TestRevokeUserApiKey:
    """
    Test suite for POST /api-keys/{api_key_id}/revoke endpoint.
    """

    @patch("modules.auth.account_security.api_keys_router.api_key_service.revoke_user_api_key")
    def test_revoke_user_api_key_success(self, mock_revoke, fast_api_client, fast_api_app):
        """Test successful key revocation returns 204 No Content."""
        # Arrange
        mock_revoke.return_value = None

        # Act
        response = fast_api_client.post(
            f"/api-keys/{KEY_ID}/revoke",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.auth.account_security.api_keys_router.api_key_service.revoke_user_api_key")
    def test_revoke_user_api_key_not_found_returns_404(self, mock_revoke, fast_api_client, fast_api_app):
        """Test that 404 is returned when the key is not found or belongs to another user."""
        # Arrange
        mock_revoke.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found for user",
        )

        # Act
        response = fast_api_client.post(
            f"/api-keys/{MISSING_KEY_ID}/revoke",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteUserApiKey:
    """
    Test suite for DELETE /api-keys/{api_key_id} endpoint.
    """

    @patch("modules.auth.account_security.api_keys_router.api_key_service.delete_user_api_key")
    def test_delete_user_api_key_success(self, mock_delete, fast_api_client, fast_api_app):
        """Test successful key deletion returns 204 No Content."""
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            f"/api-keys/{KEY_ID}",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("modules.auth.account_security.api_keys_router.api_key_service.delete_user_api_key")
    def test_delete_user_api_key_not_found_returns_404(self, mock_delete, fast_api_client, fast_api_app):
        """Test that 404 is returned when the key does not exist."""
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found for user",
        )

        # Act
        response = fast_api_client.delete(
            f"/api-keys/{MISSING_KEY_ID}",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
