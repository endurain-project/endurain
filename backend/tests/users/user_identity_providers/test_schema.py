"""Tests for user_identity_providers.schema module."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from users.user_identity_providers.schema import (
    UserIdentityProviderBase,
    UserIdentityProviderCreate,
    UserIdentityProviderRead,
    UserIdentityProviderResponse,
    UserIdentityProviderTokenUpdate,
)


class TestUserIdentityProviderBase:
    """Test suite for UserIdentityProviderBase schema."""

    def test_user_identity_provider_base_valid(self):
        """Test creating valid UserIdentityProviderBase instance.

        Asserts:
            - Valid data passes validation
            - All required fields are present
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
        }

        # Act
        obj = UserIdentityProviderBase(**data)

        # Assert
        assert obj.user_id == 1
        assert obj.idp_id == 1
        assert obj.idp_subject == "user123@example.com"

    def test_user_identity_provider_base_missing_required_field(self):
        """Test validation error when required field is missing.

        Asserts:
            - ValidationError is raised for missing user_id
        """
        # Arrange
        data = {
            "idp_id": 1,
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "user_id" in str(exc_info.value)

    def test_user_identity_provider_base_extra_fields_forbidden(self):
        """Test that extra fields are not allowed.

        Asserts:
            - ValidationError is raised for extra fields
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
            "extra_field": "should_fail",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "extra_field" in str(exc_info.value)

    def test_user_identity_provider_base_idp_subject_too_short(self):
        """Test validation for minimum idp_subject length.

        Asserts:
            - ValidationError is raised for empty idp_subject
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "idp_subject" in str(exc_info.value)

    def test_user_identity_provider_base_idp_subject_too_long(self):
        """Test validation for maximum idp_subject length.

        Asserts:
            - ValidationError is raised for idp_subject exceeding 500 chars
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "x" * 501,
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "idp_subject" in str(exc_info.value)

    def test_user_identity_provider_base_invalid_user_id_type(self):
        """Test strict int validation for user_id.

        Asserts:
            - ValidationError is raised for non-integer user_id
        """
        # Arrange
        data = {
            "user_id": "not-an-int",
            "idp_id": 1,
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "user_id" in str(exc_info.value)

    def test_user_identity_provider_base_invalid_idp_id_type(self):
        """Test strict int validation for idp_id.

        Asserts:
            - ValidationError is raised for non-integer idp_id
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": "not-an-int",
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "idp_id" in str(exc_info.value)


class TestUserIdentityProviderCreate:
    """Test suite for UserIdentityProviderCreate schema."""

    def test_user_identity_provider_create_valid(self):
        """Test creating valid UserIdentityProviderCreate instance.

        Asserts:
            - Valid data passes validation
            - Inherits validation from base class
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
        }

        # Act
        obj = UserIdentityProviderCreate(**data)

        # Assert
        assert obj.user_id == 1
        assert obj.idp_id == 1
        assert obj.idp_subject == "user123@example.com"


class TestUserIdentityProviderRead:
    """Test suite for UserIdentityProviderRead schema."""

    def test_user_identity_provider_read_valid_minimal(self):
        """Test creating UserIdentityProviderRead with required fields.

        Asserts:
            - Required fields are present
            - Optional timestamp fields can be None
        """
        # Arrange
        data = {
            "id": 1,
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
            "linked_at": datetime.now(timezone.utc),
        }

        # Act
        obj = UserIdentityProviderRead(**data)

        # Assert
        assert obj.id == 1
        assert obj.linked_at is not None
        assert obj.last_login is None

    def test_user_identity_provider_read_valid_all_fields(self):
        """Test creating UserIdentityProviderRead with all fields.

        Asserts:
            - All fields are properly stored
            - Timestamps are preserved
        """
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "id": 1,
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
            "linked_at": now,
            "last_login": now,
            "idp_access_token_expires_at": now,
            "idp_refresh_token_updated_at": now,
        }

        # Act
        obj = UserIdentityProviderRead(**data)

        # Assert
        assert obj.id == 1
        assert obj.last_login == now
        assert obj.idp_access_token_expires_at == now
        assert obj.idp_refresh_token_updated_at == now

    def test_user_identity_provider_read_missing_linked_at(self):
        """Test validation error when linked_at is missing.

        Asserts:
            - ValidationError is raised for missing linked_at
        """
        # Arrange
        data = {
            "id": 1,
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderRead(**data)

        assert "linked_at" in str(exc_info.value)


class TestUserIdentityProviderResponse:
    """Test suite for UserIdentityProviderResponse schema."""

    def test_user_identity_provider_response_valid_minimal(self):
        """Test creating UserIdentityProviderResponse with required fields.

        Asserts:
            - Required fields are present
            - Optional enriched fields default to None
        """
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "id": 1,
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
            "linked_at": now,
        }

        # Act
        obj = UserIdentityProviderResponse(**data)

        # Assert
        assert obj.id == 1
        assert obj.idp_name is None
        assert obj.idp_slug is None

    def test_user_identity_provider_response_valid_enriched(self):
        """Test creating UserIdentityProviderResponse with enriched fields.

        Asserts:
            - Enriched fields are properly stored
            - All fields are accessible
        """
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "id": 1,
            "user_id": 1,
            "idp_id": 1,
            "idp_subject": "user123@example.com",
            "linked_at": now,
            "idp_name": "Strava",
            "idp_slug": "strava",
            "idp_icon": "https://example.com/strava.svg",
            "idp_provider_type": "oauth2",
        }

        # Act
        obj = UserIdentityProviderResponse(**data)

        # Assert
        assert obj.idp_name == "Strava"
        assert obj.idp_slug == "strava"
        assert obj.idp_icon == "https://example.com/strava.svg"
        assert obj.idp_provider_type == "oauth2"

    def test_user_identity_provider_response_from_orm(self):
        """Test creating response from ORM attributes.

        Asserts:
            - from_attributes config allows creation from ORM models
        """

        # Arrange
        class MockORM:
            id = 1
            user_id = 1
            idp_id = 1
            idp_subject = "user123@example.com"
            linked_at = datetime.now(timezone.utc)
            last_login = None
            idp_access_token_expires_at = None
            idp_refresh_token_updated_at = None

        # Act
        obj = UserIdentityProviderResponse.model_validate(MockORM())

        # Assert
        assert obj.id == 1
        assert obj.idp_subject == "user123@example.com"


class TestUserIdentityProviderTokenUpdate:
    """Test suite for UserIdentityProviderTokenUpdate schema."""

    def test_user_identity_provider_token_update_valid_minimal(self):
        """Test creating UserIdentityProviderTokenUpdate with no fields.

        Asserts:
            - All fields are optional
            - Empty object is valid
        """
        # Arrange
        data = {}

        # Act
        obj = UserIdentityProviderTokenUpdate(**data)

        # Assert
        assert obj.idp_refresh_token is None
        assert obj.idp_access_token_expires_at is None
        assert obj.idp_refresh_token_updated_at is None

    def test_user_identity_provider_token_update_valid_all_fields(self):
        """Test creating TokenUpdate with all fields.

        Asserts:
            - All fields are properly stored
        """
        # Arrange
        now = datetime.now(timezone.utc)
        data = {
            "idp_refresh_token": "encrypted_token_xyz",
            "idp_access_token_expires_at": now,
            "idp_refresh_token_updated_at": now,
        }

        # Act
        obj = UserIdentityProviderTokenUpdate(**data)

        # Assert
        assert obj.idp_refresh_token == "encrypted_token_xyz"
        assert obj.idp_access_token_expires_at == now
        assert obj.idp_refresh_token_updated_at == now

    def test_user_identity_provider_token_update_extra_fields_forbidden(self):
        """Test that extra fields are not allowed.

        Asserts:
            - ValidationError is raised for extra fields
        """
        # Arrange
        data = {
            "idp_refresh_token": "token",
            "extra_field": "should_fail",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderTokenUpdate(**data)

        assert "extra_field" in str(exc_info.value)
