"""Tests for user_identity_providers.schema module."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from modules.auth.identity_provider_links.schema import (
    IdentityProviderLinkRead,
    UserIdentityProviderBase,
    UserIdentityProviderCreate,
    UserIdentityProviderRead,
)

IDP_ID = uuid.uuid4()


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
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
        }

        # Act
        obj = UserIdentityProviderBase(**data)

        # Assert
        assert obj.user_id == 1
        assert obj.idp_id == IDP_ID
        assert obj.idp_subject == "user123@example.com"

    def test_user_identity_provider_base_missing_required_field(self):
        """Test validation error when required field is missing.

        Asserts:
            - ValidationError is raised for missing user_id
        """
        # Arrange
        data = {
            "idp_id": IDP_ID,
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
            "idp_id": IDP_ID,
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
            "idp_id": IDP_ID,
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
            "idp_id": IDP_ID,
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
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderBase(**data)

        assert "user_id" in str(exc_info.value)

    @pytest.mark.parametrize("bad_idp_id", ["not-a-uuid", 1])
    def test_user_identity_provider_base_invalid_idp_id_type(self, bad_idp_id):
        """Test UUID validation for idp_id.

        Asserts:
            - ValidationError is raised for a malformed or integer idp_id
        """
        # Arrange
        data = {
            "user_id": 1,
            "idp_id": bad_idp_id,
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
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
        }

        # Act
        obj = UserIdentityProviderCreate(**data)

        # Assert
        assert obj.user_id == 1
        assert obj.idp_id == IDP_ID
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
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
            "linked_at": datetime.now(UTC),
        }

        # Act
        obj = UserIdentityProviderRead(**data)

        # Assert
        assert obj.id == uuid.UUID(int=1)
        assert obj.linked_at is not None
        assert obj.last_login is None

    def test_user_identity_provider_read_valid_all_fields(self):
        """Test creating UserIdentityProviderRead with all fields.

        Asserts:
            - All fields are properly stored
            - Timestamps are preserved
        """
        # Arrange
        now = datetime.now(UTC)
        data = {
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
            "linked_at": now,
            "last_login": now,
        }

        # Act
        obj = UserIdentityProviderRead(**data)

        # Assert
        assert obj.id == uuid.UUID(int=1)
        assert obj.last_login == now

    def test_user_identity_provider_read_missing_linked_at(self):
        """Test validation error when linked_at is missing.

        Asserts:
            - ValidationError is raised for missing linked_at
        """
        # Arrange
        data = {
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            UserIdentityProviderRead(**data)

        assert "linked_at" in str(exc_info.value)


class TestUserIdentityProviderResponse:
    """Test suite for IdentityProviderLinkRead schema."""

    def test_user_identity_provider_response_valid_minimal(self):
        """Test creating IdentityProviderLinkRead with required fields.

        Asserts:
            - Required fields are present
            - Optional enriched fields default to None
        """
        # Arrange
        now = datetime.now(UTC)
        data = {
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
            "linked_at": now,
        }

        # Act
        obj = IdentityProviderLinkRead(**data)

        # Assert
        assert obj.id == uuid.UUID(int=1)
        assert obj.idp_name is None
        assert obj.idp_slug is None

    def test_user_identity_provider_response_valid_enriched(self):
        """Test creating IdentityProviderLinkRead with enriched fields.

        Asserts:
            - Enriched fields are properly stored
            - All fields are accessible
        """
        # Arrange
        now = datetime.now(UTC)
        data = {
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "idp_id": IDP_ID,
            "idp_subject": "user123@example.com",
            "linked_at": now,
            "idp_name": "Strava",
            "idp_slug": "strava",
            "idp_icon": "https://example.com/strava.svg",
            "idp_provider_type": "oauth2",
        }

        # Act
        obj = IdentityProviderLinkRead(**data)

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
            id = uuid.UUID(int=1)
            user_id = 1
            idp_id = IDP_ID
            idp_subject = "user123@example.com"
            linked_at = datetime.now(UTC)
            last_login = None

        # Act
        obj = IdentityProviderLinkRead.model_validate(MockORM())

        # Assert
        assert obj.id == uuid.UUID(int=1)
        assert obj.idp_subject == "user123@example.com"


class TestLinkReadHoldsNoTokenMetadata:
    """The link carries no token data: tokens belong to sessions."""

    def test_a_link_has_no_token_fields(self):
        assert not {name for name in UserIdentityProviderRead.model_fields if "token" in name}
        assert not {name for name in IdentityProviderLinkRead.model_fields if "token" in name}
