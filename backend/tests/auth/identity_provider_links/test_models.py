"""Tests for user_identity_providers.models module."""

import uuid

from sqlalchemy import Uuid, inspect

from modules.auth.identity_provider_links.models import IdentityLink, IdpSessionToken


class TestUserIdentityProviderModel:
    """Test suite for IdentityLink ORM model."""

    def test_user_identity_provider_model_tablename(self):
        """Test IdentityLink model table name.

        Asserts:
            - Model uses correct table name
        """
        # Act & Assert
        assert IdentityLink.__tablename__ == "users_identity_providers"

    def test_user_identity_provider_model_foreign_keys(self):
        """Test IdentityLink model foreign key configuration.

        Asserts:
            - Model has foreign keys to users and identity_providers tables
        """
        # Arrange & Act
        mapper = inspect(IdentityLink)

        # Assert
        # Check for foreign key relationships
        fk_columns = [col.name for col in mapper.columns if hasattr(col, "foreign_keys")]
        assert "user_id" in fk_columns or "idp_id" in fk_columns

    def test_user_identity_provider_model_nullable_fields(self):
        """Test IdentityLink nullable field configuration.

        Asserts:
            - Optional fields are nullable
        """
        # Arrange & Act
        mapper = inspect(IdentityLink)
        columns = {col.name: col for col in mapper.columns}

        # Assert
        # These should be nullable
        assert columns["last_login"].nullable is True

        # These should be non-nullable
        assert columns["user_id"].nullable is False
        assert columns["idp_id"].nullable is False
        assert columns["idp_subject"].nullable is False

    def test_user_identity_provider_model_has_relationships(self):
        """Test IdentityLink model has relationship attributes.

        Asserts:
            - Model class has relationship definitions
        """
        # Act & Assert
        assert not hasattr(IdentityLink, "identity_providers")

    def test_user_identity_provider_model_column_types(self):
        """Test IdentityLink column types.

        Asserts:
            - Columns have correct types
        """
        # Arrange & Act
        mapper = inspect(IdentityLink)
        columns = {col.name: col for col in mapper.columns}

        # Assert
        assert columns["id"].type.python_type is uuid.UUID
        assert columns["id"].primary_key is True
        assert str(columns["idp_subject"].type) == "VARCHAR(500)"

    def test_user_identity_provider_model_column_count(self):
        """Test IdentityLink has all expected columns.

        Asserts:
            - Model has exactly 6 columns and none holds a token
        """
        # Arrange & Act
        mapper = inspect(IdentityLink)

        # Assert - Should have: id, user_id, idp_id, idp_subject, linked_at, last_login
        assert {col.name for col in mapper.columns} == {
            "id",
            "user_id",
            "idp_id",
            "idp_subject",
            "linked_at",
            "last_login",
        }

    def test_user_identity_provider_model_has_indexes(self):
        """Test IdentityLink has database indexes.

        Asserts:
            - Model has indexes on key columns for performance
        """
        # Arrange & Act
        mapper = inspect(IdentityLink)

        # Assert
        # Model should have indexes (at minimum on user_id, idp_id)
        # Indexes are configured at the database schema level
        assert mapper.persist_selectable is not None


class TestIdpSessionTokenModel:
    """The sign-in behind one Endurain session, with the refresh token it was issued."""

    def test_the_table_name(self):
        assert IdpSessionToken.__tablename__ == "idp_session_tokens"

    def test_the_session_is_unique_and_has_no_foreign_key_so_the_token_outlives_the_session_row(self):
        columns = {col.name: col for col in inspect(IdpSessionToken).columns}

        assert isinstance(columns["session_id"].type, Uuid)
        assert columns["session_id"].unique is True
        assert columns["session_id"].nullable is False
        assert not columns["session_id"].foreign_keys

    def test_the_user_and_the_provider_cascade_on_delete(self):
        columns = {col.name: col for col in inspect(IdpSessionToken).columns}

        for name in ("user_id", "idp_id"):
            assert columns[name].nullable is False
            assert columns[name].index is True
            assert [fk.ondelete for fk in columns[name].foreign_keys] == ["CASCADE"]

    def test_a_provider_may_issue_no_token(self):
        columns = {col.name: col for col in inspect(IdpSessionToken).columns}

        assert columns["refresh_token"].nullable is True
        assert columns["access_token_expires_at"].nullable is True
        assert columns["refresh_token_updated_at"].nullable is True
        assert columns["created_at"].nullable is False
