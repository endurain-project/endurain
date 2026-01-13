"""Tests for user_integrations.models module."""

import pytest

from users.user_integrations.models import UsersIntegrations


class TestUsersIntegrationsModel:
    """Test suite for UsersIntegrations ORM model."""

    def test_users_integrations_table_name(self):
        """Test that model maps to correct table.

        Asserts:
            - Table name is 'users_integrations'
        """
        # Assert
        assert UsersIntegrations.__tablename__ == "users_integrations"

    def test_users_integrations_has_id_column(self):
        """Test that model has id column.

        Asserts:
            - id column exists as primary key
        """
        # Assert
        assert hasattr(UsersIntegrations, "id")
        assert UsersIntegrations.id.primary_key

    def test_users_integrations_has_user_id_column(self):
        """Test that model has user_id column.

        Asserts:
            - user_id column exists with unique constraint
        """
        # Assert
        assert hasattr(UsersIntegrations, "user_id")
        # Verify uniqueness
        unique_constraints = [
            c
            for c in UsersIntegrations.__table__.constraints
            if hasattr(c, "columns") and "user_id" in [col.name for col in c.columns]
        ]
        assert len(unique_constraints) > 0

    def test_users_integrations_has_all_columns(self):
        """Test that model has all required columns.

        Asserts:
            - All 12 columns exist
        """
        # Arrange
        expected_columns = [
            "id",
            "user_id",
            "strava_client_id",
            "strava_client_secret",
            "strava_state",
            "strava_token",
            "strava_refresh_token",
            "strava_token_expires_at",
            "strava_sync_gear",
            "garminconnect_oauth1",
            "garminconnect_oauth2",
            "garminconnect_sync_gear",
        ]

        # Assert
        for column in expected_columns:
            assert hasattr(UsersIntegrations, column)

    def test_users_integrations_strava_columns_nullable(self):
        """Test that Strava columns are nullable.

        Asserts:
            - All Strava columns are nullable
        """
        # Arrange
        strava_columns = [
            "strava_client_id",
            "strava_client_secret",
            "strava_state",
            "strava_token",
            "strava_refresh_token",
            "strava_token_expires_at",
        ]

        # Assert
        for col_name in strava_columns:
            column = UsersIntegrations.__table__.columns[col_name]
            assert column.nullable, f"{col_name} should be nullable"

    def test_users_integrations_garmin_columns_nullable(self):
        """Test that Garmin columns are nullable.

        Asserts:
            - All Garmin columns are nullable
        """
        # Arrange
        garmin_columns = [
            "garminconnect_oauth1",
            "garminconnect_oauth2",
        ]

        # Assert
        for col_name in garmin_columns:
            column = UsersIntegrations.__table__.columns[col_name]
            assert column.nullable, f"{col_name} should be nullable"

    def test_users_integrations_sync_gear_columns_not_nullable(self):
        """Test that sync_gear boolean columns are NOT nullable.

        Asserts:
            - sync_gear columns have NOT NULL constraint
        """
        # Arrange
        sync_gear_columns = [
            "strava_sync_gear",
            "garminconnect_sync_gear",
        ]

        # Assert
        for col_name in sync_gear_columns:
            column = UsersIntegrations.__table__.columns[col_name]
            assert not column.nullable, f"{col_name} should NOT be nullable"

    def test_users_integrations_has_user_relationship(self):
        """Test that model has user relationship.

        Asserts:
            - Relationship to Users model exists
        """
        # Assert
        assert hasattr(UsersIntegrations, "user")

    def test_users_integrations_user_id_foreign_key(self):
        """Test that user_id has foreign key constraint.

        Asserts:
            - user_id foreign key constraint exists
        """
        # Assert
        # Check that foreign keys are defined on the table
        foreign_keys = list(UsersIntegrations.__table__.foreign_keys)
        assert len(foreign_keys) > 0, "Table should have foreign key constraints"

    def test_users_integrations_user_id_indexed(self):
        """Test that user_id is indexed.

        Asserts:
            - user_id has an index
        """
        # Arrange
        indexes = UsersIntegrations.__table__.indexes

        # Assert
        user_id_indexes = [
            idx for idx in indexes if "user_id" in [col.name for col in idx.columns]
        ]
        assert len(user_id_indexes) > 0


class TestUsersIntegrationsModelStructure:
    """Structure tests for UsersIntegrations model (no ORM instantiation)."""

    def test_users_integrations_strava_token_expires_at_type(self):
        """Test that strava_token_expires_at is datetime type.

        Asserts:
            - Column is datetime type
        """
        # Assert
        from sqlalchemy import DateTime

        column = UsersIntegrations.__table__.columns["strava_token_expires_at"]
        assert isinstance(column.type, DateTime)

    def test_users_integrations_garminconnect_oauth_json_type(self):
        """Test that garminconnect_oauth columns are JSON type.

        Asserts:
            - Columns are JSON type for dict storage
        """
        # Assert
        from sqlalchemy import JSON

        oauth1_col = UsersIntegrations.__table__.columns["garminconnect_oauth1"]
        oauth2_col = UsersIntegrations.__table__.columns["garminconnect_oauth2"]
        assert isinstance(oauth1_col.type, JSON)
        assert isinstance(oauth2_col.type, JSON)
