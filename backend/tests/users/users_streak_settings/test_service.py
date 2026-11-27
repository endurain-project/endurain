"""Tests for the streak settings service."""

from unittest.mock import MagicMock, patch

import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streak_settings.service as streak_settings_service
from tests._helpers.auth import MOCK_USER_ID


class TestStreakSettingsService:
    @patch("modules.users.users_streak_settings.service.streak_settings_crud.get_streak_settings_by_user_id")
    def test_get_settings_reads_without_committing(self, mock_get):
        """Reads the stored settings and leaves the transaction alone."""
        db = MagicMock()
        mock_get.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=MOCK_USER_ID)

        assert streak_settings_service.get_settings(MOCK_USER_ID, db) is mock_get.return_value

        mock_get.assert_called_once_with(MOCK_USER_ID, db)
        db.commit.assert_not_called()

    @patch("modules.users.users_streak_settings.service.streak_settings_crud.stage_streak_settings")
    def test_update_settings_commits(self, mock_stage):
        """Stages the new settings and commits them."""
        db = MagicMock()
        payload = streak_settings_schema.UsersStreakSettingsUpdate(min_activities_per_week=2)
        mock_stage.return_value = streak_settings_schema.UsersStreakSettingsRead(
            user_id=MOCK_USER_ID, min_activities_per_week=2
        )

        result = streak_settings_service.update_settings(MOCK_USER_ID, payload, db)

        assert result is mock_stage.return_value
        mock_stage.assert_called_once_with(MOCK_USER_ID, payload, db)
        db.commit.assert_called_once()
