import pytest

import users.users_session.rotated_refresh_tokens.models as rotated_token_models


class TestRotatedRefreshTokenModel:
    """
    Test suite for RotatedRefreshToken SQLAlchemy model.
    """

    def test_rotated_refresh_token_model_table_name(self):
        """
        Test RotatedRefreshToken model has correct table name.
        """
        # Assert
        assert (
            rotated_token_models.RotatedRefreshToken.__tablename__
            == "rotated_refresh_tokens"
        )

    def test_rotated_refresh_token_model_columns_exist(self):
        """
        Test RotatedRefreshToken model has all expected columns.
        """
        # Assert
        model = rotated_token_models.RotatedRefreshToken
        assert hasattr(model, "id")
        assert hasattr(model, "token_family_id")
        assert hasattr(model, "hashed_token")
        assert hasattr(model, "rotation_count")
        assert hasattr(model, "rotated_at")
        assert hasattr(model, "expires_at")

    def test_rotated_refresh_token_model_primary_key(self):
        """
        Test RotatedRefreshToken model has correct primary key.
        """
        # Arrange
        id_column = rotated_token_models.RotatedRefreshToken.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_rotated_refresh_token_model_foreign_key(self):
        """
        Test RotatedRefreshToken model has correct foreign key.
        """
        # Arrange
        token_family_id_column = (
            rotated_token_models.RotatedRefreshToken.token_family_id
        )

        # Assert
        assert token_family_id_column.nullable is False
        assert token_family_id_column.index is True

    def test_rotated_refresh_token_model_required_fields(self):
        """
        Test RotatedRefreshToken model required fields.
        """
        # Arrange
        model = rotated_token_models.RotatedRefreshToken

        # Assert
        assert model.token_family_id.nullable is False
        assert model.hashed_token.nullable is False
        assert model.rotation_count.nullable is False
        assert model.rotated_at.nullable is False
        assert model.expires_at.nullable is False

    def test_rotated_refresh_token_model_column_types(self):
        """
        Test RotatedRefreshToken model column types.
        """
        # Arrange
        model = rotated_token_models.RotatedRefreshToken

        # Assert
        assert model.id.type.python_type == int
        assert model.token_family_id.type.python_type == str
        assert model.hashed_token.type.python_type == str
        assert model.rotation_count.type.python_type == int

    def test_rotated_refresh_token_model_string_lengths(self):
        """
        Test RotatedRefreshToken model string column lengths.
        """
        # Arrange
        model = rotated_token_models.RotatedRefreshToken

        # Assert
        assert model.token_family_id.type.length == 36
        assert model.hashed_token.type.length == 255

    def test_rotated_refresh_token_model_unique_hashed_token(self):
        """
        Test RotatedRefreshToken model hashed_token is unique.
        """
        # Arrange
        hashed_token_column = rotated_token_models.RotatedRefreshToken.hashed_token

        # Assert
        assert hashed_token_column.unique is True

    def test_rotated_refresh_token_model_has_relationship(self):
        """
        Test RotatedRefreshToken model has expected relationship.
        """
        # Arrange
        model = rotated_token_models.RotatedRefreshToken

        # Assert
        assert hasattr(model, "users_session")
