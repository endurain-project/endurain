"""Tests for user_integrations.schema module."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from users.users_integrations.schema import (
    UsersIntegrationsBase,
    UsersIntegrationsCreate,
    UsersIntegrationsRead,
    UsersIntegrationsUpdate,
)


class TestUsersIntegrationsBase:
    """Test suite for UsersIntegrationsBase schema."""

    def test_users_integrations_base_valid_minimal(self):
        """Test creating valid UsersIntegrationsBase with minimal fields.

        Asserts:
            - All fields are optional and default to None/False
        """
        # Arrange
        data = {}

        # Act
        obj = UsersIntegrationsBase(**data)

        # Assert
        assert obj.strava_client_id is None
        assert obj.strava_client_secret is None
        assert obj.strava_state is None
        assert obj.strava_token is None
        assert obj.strava_refresh_token is None
        assert obj.strava_token_expires_at is None
        assert obj.strava_sync_gear is False
        assert obj.garminconnect_oauth1 is None
        assert obj.garminconnect_oauth2 is None
        assert obj.garminconnect_sync_gear is False

    def test_users_integrations_base_valid_all_fields(self):
        """Test creating UsersIntegrationsBase with all fields.

        Asserts:
            - All fields are properly stored
        """
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "strava_client_id": "client_id",
            "strava_client_secret": "client_secret",
            "strava_state": "state123",
            "strava_token": "token",
            "strava_refresh_token": "refresh",
            "strava_token_expires_at": now,
            "strava_sync_gear": True,
            "garminconnect_oauth1": {"key": "value"},
            "garminconnect_oauth2": {"key": "value"},
            "garminconnect_sync_gear": True,
        }

        # Act
        obj = UsersIntegrationsBase(**data)

        # Assert
        assert obj.strava_client_id == "client_id"
        assert obj.strava_client_secret == "client_secret"
        assert obj.strava_state == "state123"
        assert obj.strava_token == "token"
        assert obj.strava_refresh_token == "refresh"
        assert obj.strava_token_expires_at == now
        assert obj.strava_sync_gear is True
        assert obj.garminconnect_oauth1 == {"key": "value"}
        assert obj.garminconnect_oauth2 == {"key": "value"}
        assert obj.garminconnect_sync_gear is True

    def test_users_integrations_base_extra_fields_forbidden(self):
        """Test that extra fields are not allowed.

        Asserts:
            - ValidationError is raised for extra fields
        """
        # Arrange
        data = {
            "strava_client_id": "client_id",
            "extra_field": "should_fail",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsBase(**data)

        assert "extra_field" in str(exc_info.value)

    def test_users_integrations_base_invalid_string_length(self):
        """Test validation for maximum string lengths.

        Asserts:
            - ValidationError for strings exceeding max length
        """
        # Arrange
        data = {
            "strava_client_id": "x" * 513,  # Max is 512
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsBase(**data)

        assert "strava_client_id" in str(exc_info.value)

    def test_users_integrations_base_invalid_strava_state_length(self):
        """Test validation for strava_state maximum length.

        Asserts:
            - ValidationError for state exceeding 45 chars
        """
        # Arrange
        data = {
            "strava_state": "x" * 46,  # Max is 45
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsBase(**data)

        assert "strava_state" in str(exc_info.value)

    def test_users_integrations_base_invalid_sync_gear_type(self):
        """Test strict bool validation for sync_gear fields.

        Asserts:
            - ValidationError for non-boolean sync_gear values
        """
        # Arrange
        data = {
            "strava_sync_gear": "true",  # Should be bool, not string
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsBase(**data)

        assert "strava_sync_gear" in str(exc_info.value)


class TestUsersIntegrationsCreate:
    """Test suite for UsersIntegrationsCreate schema."""

    def test_users_integrations_create_valid(self):
        """Test creating UsersIntegrationsCreate instance.

        Asserts:
            - Valid data passes validation
            - Inherits from base class
        """
        # Arrange
        data = {
            "strava_client_id": "client_id",
            "strava_sync_gear": True,
        }

        # Act
        obj = UsersIntegrationsCreate(**data)

        # Assert
        assert obj.strava_client_id == "client_id"
        assert obj.strava_sync_gear is True


class TestUsersIntegrationsRead:
    """Test suite for UsersIntegrationsRead schema."""

    def test_users_integrations_read_valid_minimal(self):
        """Test creating UsersIntegrationsRead with required fields.

        Asserts:
            - id and user_id are required
        """
        # Arrange
        data = {
            "id": 1,
            "user_id": 1,
        }

        # Act
        obj = UsersIntegrationsRead(**data)

        # Assert
        assert obj.id == 1
        assert obj.user_id == 1

    def test_users_integrations_read_missing_id(self):
        """Test validation error when id is missing.

        Asserts:
            - ValidationError is raised
        """
        # Arrange
        data = {
            "user_id": 1,
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsRead(**data)

        assert "id" in str(exc_info.value)

    def test_users_integrations_read_missing_user_id(self):
        """Test validation error when user_id is missing.

        Asserts:
            - ValidationError is raised
        """
        # Arrange
        data = {
            "id": 1,
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsRead(**data)

        assert "user_id" in str(exc_info.value)

    def test_users_integrations_read_invalid_id_type(self):
        """Test strict int validation for id.

        Asserts:
            - ValidationError for non-integer id
        """
        # Arrange
        data = {
            "id": "not-an-int",
            "user_id": 1,
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UsersIntegrationsRead(**data)

        assert "id" in str(exc_info.value)


class TestUsersIntegrationsUpdate:
    """Test suite for UsersIntegrationsUpdate schema."""

    def test_users_integrations_update_valid_empty(self):
        """Test creating UsersIntegrationsUpdate with no fields.

        Asserts:
            - All fields are optional
        """
        # Arrange
        data = {}

        # Act
        obj = UsersIntegrationsUpdate(**data)

        # Assert
        assert obj.strava_sync_gear is False

    def test_users_integrations_update_valid_partial(self):
        """Test updating with partial fields.

        Asserts:
            - Only specified fields are updated
        """
        # Arrange
        data = {
            "strava_client_id": "new_client_id",
            "garminconnect_sync_gear": True,
        }

        # Act
        obj = UsersIntegrationsUpdate(**data)

        # Assert
        assert obj.strava_client_id == "new_client_id"
        assert obj.garminconnect_sync_gear is True
        assert obj.strava_sync_gear is False  # Default

    def test_users_integrations_update_from_orm(self):
        """Test creating from ORM attributes.

        Asserts:
            - from_attributes config allows ORM conversion
        """

        # Arrange
        class MockORM:
            strava_client_id = "client_id"
            strava_sync_gear = True
            garminconnect_oauth1 = {"key": "value"}
            garminconnect_oauth2 = None
            garminconnect_sync_gear = False
            strava_client_secret = None
            strava_state = None
            strava_token = None
            strava_refresh_token = None
            strava_token_expires_at = None

        # Act
        obj = UsersIntegrationsUpdate.model_validate(MockORM())

        # Assert
        assert obj.strava_client_id == "client_id"
        assert obj.strava_sync_gear is True
