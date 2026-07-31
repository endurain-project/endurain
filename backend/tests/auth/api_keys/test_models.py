"""Tests for users_api_keys database models."""

import modules.auth.api_keys.models as users_api_keys_models


class TestUsersApiKeysModel:
    """
    Test suite for UsersApiKeys SQLAlchemy model.
    """

    def test_users_api_keys_model_table_name(self):
        """Test UsersApiKeys model has correct table name."""
        assert users_api_keys_models.UsersApiKeys.__tablename__ == "users_api_keys"

    def test_users_api_keys_model_columns_exist(self):
        """Test UsersApiKeys model has all expected columns."""
        model = users_api_keys_models.UsersApiKeys
        assert hasattr(model, "id")
        assert hasattr(model, "user_id")
        assert hasattr(model, "name")
        assert hasattr(model, "key_prefix")
        assert hasattr(model, "key_hash")
        assert hasattr(model, "scopes")
        assert hasattr(model, "expires_at")
        assert hasattr(model, "last_used_at")
        assert hasattr(model, "created_at")
        assert hasattr(model, "is_active")

    def test_users_api_keys_model_id_primary_key(self):
        """Test id column is a primary key."""
        id_column = users_api_keys_models.UsersApiKeys.id
        assert id_column.primary_key is True

    def test_users_api_keys_model_id_not_nullable(self):
        """Test id column is not nullable."""
        id_column = users_api_keys_models.UsersApiKeys.id
        assert id_column.nullable is False

    def test_users_api_keys_model_id_type(self):
        """Test id column is a String type."""
        id_column = users_api_keys_models.UsersApiKeys.id
        assert id_column.type.python_type is str

    def test_users_api_keys_model_user_id_not_nullable(self):
        """Test user_id column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.user_id.nullable is False

    def test_users_api_keys_model_user_id_indexed(self):
        """Test user_id column is indexed."""
        assert users_api_keys_models.UsersApiKeys.user_id.index is True

    def test_users_api_keys_model_name_not_nullable(self):
        """Test name column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.name.nullable is False

    def test_users_api_keys_model_name_type(self):
        """Test name column is String type."""
        assert users_api_keys_models.UsersApiKeys.name.type.python_type is str

    def test_users_api_keys_model_key_prefix_not_nullable(self):
        """Test key_prefix column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.key_prefix.nullable is False

    def test_users_api_keys_model_key_prefix_type(self):
        """Test key_prefix column is String type."""
        assert users_api_keys_models.UsersApiKeys.key_prefix.type.python_type is str

    def test_users_api_keys_model_key_hash_not_nullable(self):
        """Test key_hash column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.key_hash.nullable is False

    def test_users_api_keys_model_key_hash_unique(self):
        """Test key_hash column has a unique constraint."""
        assert users_api_keys_models.UsersApiKeys.key_hash.unique is True

    def test_users_api_keys_model_key_hash_indexed(self):
        """Test key_hash column is indexed."""
        assert users_api_keys_models.UsersApiKeys.key_hash.index is True

    def test_users_api_keys_model_key_hash_type(self):
        """Test key_hash column is String type."""
        assert users_api_keys_models.UsersApiKeys.key_hash.type.python_type is str

    def test_users_api_keys_model_scopes_not_nullable(self):
        """Test scopes column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.scopes.nullable is False

    def test_users_api_keys_model_expires_at_nullable(self):
        """Test expires_at column is nullable (no expiry means NULL)."""
        assert users_api_keys_models.UsersApiKeys.expires_at.nullable is True

    def test_users_api_keys_model_last_used_at_nullable(self):
        """Test last_used_at column is nullable (not yet used means NULL)."""
        assert users_api_keys_models.UsersApiKeys.last_used_at.nullable is True

    def test_users_api_keys_model_created_at_not_nullable(self):
        """Test created_at column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.created_at.nullable is False

    def test_users_api_keys_model_is_active_not_nullable(self):
        """Test is_active column is not nullable."""
        assert users_api_keys_models.UsersApiKeys.is_active.nullable is False
