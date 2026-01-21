import pytest

import users.users_sessions.models as users_session_models


class TestUsersSessionsModel:
    """
    Test suite for UsersSessions SQLAlchemy model.
    """

    def test_users_sessions_model_table_name(self):
        """
        Test UsersSessions model has correct table name.
        """
        # Assert
        assert users_session_models.UsersSessions.__tablename__ == "users_sessions"

    def test_users_sessions_model_columns_exist(self):
        """
        Test UsersSessions model has all expected columns.
        """
        # Assert
        model = users_session_models.UsersSessions
        assert hasattr(model, "id")
        assert hasattr(model, "user_id")
        assert hasattr(model, "refresh_token")
        assert hasattr(model, "ip_address")
        assert hasattr(model, "device_type")
        assert hasattr(model, "operating_system")
        assert hasattr(model, "operating_system_version")
        assert hasattr(model, "browser")
        assert hasattr(model, "browser_version")
        assert hasattr(model, "created_at")
        assert hasattr(model, "last_activity_at")
        assert hasattr(model, "expires_at")
        assert hasattr(model, "oauth_state_id")
        assert hasattr(model, "tokens_exchanged")
        assert hasattr(model, "token_family_id")
        assert hasattr(model, "rotation_count")
        assert hasattr(model, "last_rotation_at")
        assert hasattr(model, "csrf_token_hash")

    def test_users_sessions_model_primary_key(self):
        """
        Test UsersSessions model has correct primary key.
        """
        # Arrange
        id_column = users_session_models.UsersSessions.id

        # Assert
        assert id_column.primary_key is True

    def test_users_sessions_model_foreign_key(self):
        """
        Test UsersSessions model has correct foreign key.
        """
        # Arrange
        user_id_column = users_session_models.UsersSessions.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_users_sessions_model_required_fields(self):
        """
        Test UsersSessions model required fields.
        """
        # Arrange
        model = users_session_models.UsersSessions

        # Assert
        assert model.id.nullable is False
        assert model.user_id.nullable is False
        assert model.refresh_token.nullable is True
        assert model.ip_address.nullable is False
        assert model.device_type.nullable is False
        assert model.operating_system.nullable is False
        assert model.operating_system_version.nullable is False
        assert model.browser.nullable is False
        assert model.browser_version.nullable is False
        assert model.created_at.nullable is False
        assert model.last_activity_at.nullable is False
        assert model.expires_at.nullable is False
        assert model.token_family_id.nullable is False

    def test_users_sessions_model_optional_fields(self):
        """
        Test UsersSessions model optional fields.
        """
        # Arrange
        model = users_session_models.UsersSessions

        # Assert
        assert model.oauth_state_id.nullable is True
        assert model.last_rotation_at.nullable is True
        assert model.csrf_token_hash.nullable is True

    def test_users_sessions_model_column_types(self):
        """
        Test UsersSessions model column types.
        """
        # Arrange
        model = users_session_models.UsersSessions

        # Assert
        assert model.id.type.python_type == str
        assert model.refresh_token.type.python_type == str
        assert model.ip_address.type.python_type == str
        assert model.device_type.type.python_type == str
        assert model.operating_system.type.python_type == str
        assert model.browser.type.python_type == str
        assert model.token_family_id.type.python_type == str

    def test_users_sessions_model_string_lengths(self):
        """
        Test UsersSessions model string column lengths.
        """
        # Arrange
        model = users_session_models.UsersSessions

        # Assert
        assert model.id.type.length == 36
        assert model.refresh_token.type.length == 255
        assert model.ip_address.type.length == 45
        assert model.device_type.type.length == 45
        assert model.operating_system.type.length == 45
        assert model.browser.type.length == 45

    def test_users_sessions_model_has_relationships(self):
        """
        Test UsersSessions model has expected relationships.
        """
        # Arrange
        model = users_session_models.UsersSessions

        # Assert
        assert hasattr(model, "users")
        assert hasattr(model, "oauth_state")
        assert hasattr(model, "rotated_refresh_tokens")

    def test_users_sessions_model_tokens_exchanged_default(self):
        """
        Test UsersSessions model tokens_exchanged default value.
        """
        # Arrange
        column = users_session_models.UsersSessions.tokens_exchanged

        # Assert
        assert column.default is not None
        assert column.default.arg is False

    def test_users_sessions_model_rotation_count_default(self):
        """
        Test UsersSessions model rotation_count default value.
        """
        # Arrange
        column = users_session_models.UsersSessions.rotation_count

        # Assert
        assert column.default is not None
        assert column.default.arg == 0
