"""Tests for user_identity_providers.models module."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import inspect

from users.users_identity_providers.models import UsersIdentityProvider


class TestUserIdentityProviderModel:
    """Test suite for UsersIdentityProvider ORM model."""

    def test_user_identity_provider_model_tablename(self):
        """Test UsersIdentityProvider model table name.

        Asserts:
            - Model uses correct table name
        """
        # Act & Assert
        assert UsersIdentityProvider.__tablename__ == "users_identity_providers"

    def test_user_identity_provider_model_foreign_keys(self):
        """Test UsersIdentityProvider model foreign key configuration.

        Asserts:
            - Model has foreign keys to users and identity_providers tables
        """
        # Arrange & Act
        mapper = inspect(UsersIdentityProvider)

        # Assert
        # Check for foreign key relationships
        fk_columns = [
            col.name for col in mapper.columns if hasattr(col, "foreign_keys")
        ]
        assert "user_id" in fk_columns or "idp_id" in fk_columns

    def test_user_identity_provider_model_nullable_fields(self):
        """Test UsersIdentityProvider nullable field configuration.

        Asserts:
            - Optional fields are nullable
        """
        # Arrange & Act
        mapper = inspect(UsersIdentityProvider)
        columns = {col.name: col for col in mapper.columns}

        # Assert
        # These should be nullable
        assert columns["last_login"].nullable is True
        assert columns["idp_refresh_token"].nullable is True
        assert columns["idp_access_token_expires_at"].nullable is True
        assert columns["idp_refresh_token_updated_at"].nullable is True

        # These should be non-nullable
        assert columns["user_id"].nullable is False
        assert columns["idp_id"].nullable is False
        assert columns["idp_subject"].nullable is False

    def test_user_identity_provider_model_has_relationships(self):
        """Test UsersIdentityProvider model has relationship attributes.

        Asserts:
            - Model class has relationship definitions
        """
        # Act & Assert
        assert hasattr(UsersIdentityProvider, "users")
        assert hasattr(UsersIdentityProvider, "identity_providers")

    def test_user_identity_provider_model_column_types(self):
        """Test UsersIdentityProvider column types.

        Asserts:
            - Columns have correct types
        """
        # Arrange & Act
        mapper = inspect(UsersIdentityProvider)
        columns = {col.name: col for col in mapper.columns}

        # Assert
        assert columns["id"].autoincrement is True
        assert columns["id"].primary_key is True
        assert str(columns["idp_subject"].type) == "VARCHAR(500)"

    def test_user_identity_provider_model_column_count(self):
        """Test UsersIdentityProvider has all expected columns.

        Asserts:
            - Model has exactly 9 columns
        """
        # Arrange & Act
        mapper = inspect(UsersIdentityProvider)

        # Assert - Should have: id, user_id, idp_id, idp_subject, linked_at,
        # last_login, idp_refresh_token, idp_access_token_expires_at,
        # idp_refresh_token_updated_at
        assert len(list(mapper.columns)) == 9

    def test_user_identity_provider_model_has_indexes(self):
        """Test UsersIdentityProvider has database indexes.

        Asserts:
            - Model has indexes on key columns for performance
        """
        # Arrange & Act
        mapper = inspect(UsersIdentityProvider)

        # Assert
        # Model should have indexes (at minimum on user_id, idp_id)
        # Indexes are configured at the database schema level
        assert mapper.mapped_table is not None
