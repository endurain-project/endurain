import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

import users.users_session.rotated_refresh_tokens.schema as rotated_token_schema


class TestRotatedRefreshTokenCreateSchema:
    """
    Test suite for RotatedRefreshTokenCreate Pydantic schema.
    """

    def test_create_schema_valid_instance(self):
        """
        Test RotatedRefreshTokenCreate schema with valid data.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        token = rotated_token_schema.RotatedRefreshTokenCreate(
            token_family_id="test-family-id",
            hashed_token="hashed-token-value",
            rotation_count=0,
            rotated_at=now,
            expires_at=now,
        )

        # Assert
        assert token.token_family_id == "test-family-id"
        assert token.hashed_token == "hashed-token-value"
        assert token.rotation_count == 0
        assert token.rotated_at == now
        assert token.expires_at == now

    def test_create_schema_requires_token_family_id(self):
        """
        Test RotatedRefreshTokenCreate requires token_family_id.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                hashed_token="hashed-token-value",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "token_family_id" in str(exc_info.value)

    def test_create_schema_requires_hashed_token(self):
        """
        Test RotatedRefreshTokenCreate requires hashed_token.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id="test-family-id",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "hashed_token" in str(exc_info.value)

    def test_create_schema_rotation_count_non_negative(self):
        """
        Test RotatedRefreshTokenCreate rotation_count must be >= 0.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id="test-family-id",
                hashed_token="hashed-token-value",
                rotation_count=-1,
                rotated_at=now,
                expires_at=now,
            )

        assert "rotation_count" in str(exc_info.value)

    def test_create_schema_token_family_id_max_length(self):
        """
        Test RotatedRefreshTokenCreate token_family_id max length.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        long_family_id = "a" * 40  # Exceeds 36 character limit

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id=long_family_id,
                hashed_token="hashed-token-value",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "token_family_id" in str(exc_info.value)

    def test_create_schema_hashed_token_max_length(self):
        """
        Test RotatedRefreshTokenCreate hashed_token max length.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        long_token = "a" * 260  # Exceeds 255 character limit

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id="test-family-id",
                hashed_token=long_token,
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "hashed_token" in str(exc_info.value)

    def test_create_schema_forbid_extra_fields(self):
        """
        Test RotatedRefreshTokenCreate forbids extra fields.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id="test-family-id",
                hashed_token="hashed-token-value",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
                extra_field="not allowed",
            )

        assert "extra_field" in str(exc_info.value)

    def test_create_schema_from_attributes(self):
        """
        Test RotatedRefreshTokenCreate has from_attributes config.
        """
        # Assert
        assert (
            rotated_token_schema.RotatedRefreshTokenCreate.model_config.get(
                "from_attributes"
            )
            is True
        )

    def test_create_schema_strict_int_validation(self):
        """
        Test RotatedRefreshTokenCreate enforces strict int types.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenCreate(
                token_family_id="test-family-id",
                hashed_token="hashed-token-value",
                rotation_count="not-an-int",
                rotated_at=now,
                expires_at=now,
            )

        assert "rotation_count" in str(exc_info.value)


class TestRotatedRefreshTokenReadSchema:
    """
    Test suite for RotatedRefreshTokenRead Pydantic schema.
    """

    def test_read_schema_includes_id(self):
        """
        Test RotatedRefreshTokenRead includes id field.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        token = rotated_token_schema.RotatedRefreshTokenRead(
            id=1,
            token_family_id="test-family-id",
            hashed_token="hashed-token-value",
            rotation_count=0,
            rotated_at=now,
            expires_at=now,
        )

        # Assert
        assert token.id == 1

    def test_read_schema_requires_id(self):
        """
        Test RotatedRefreshTokenRead requires id field.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenRead(
                token_family_id="test-family-id",
                hashed_token="hashed-token-value",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "id" in str(exc_info.value)

    def test_read_schema_id_positive(self):
        """
        Test RotatedRefreshTokenRead id must be >= 1.
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            rotated_token_schema.RotatedRefreshTokenRead(
                id=0,
                token_family_id="test-family-id",
                hashed_token="hashed-token-value",
                rotation_count=0,
                rotated_at=now,
                expires_at=now,
            )

        assert "id" in str(exc_info.value)

    def test_read_schema_inherits_from_create(self):
        """
        Test RotatedRefreshTokenRead inherits from RotatedRefreshTokenCreate.
        """
        # Assert
        assert issubclass(
            rotated_token_schema.RotatedRefreshTokenRead,
            rotated_token_schema.RotatedRefreshTokenCreate,
        )

    def test_read_schema_from_attributes(self):
        """
        Test RotatedRefreshTokenRead has from_attributes config.
        """
        # Assert
        assert (
            rotated_token_schema.RotatedRefreshTokenRead.model_config.get(
                "from_attributes"
            )
            is True
        )
