"""Tests for the activity thumbnail scheduled jobs."""

from unittest.mock import MagicMock, patch

MODULE = "modules.activities.activity_thumbnail.scheduled_jobs"


class TestMaintenanceEntryPoints:
    @patch(f"{MODULE}.activity_thumbnail_service")
    @patch(f"{MODULE}.core_database.SessionLocal")
    @patch(f"{MODULE}.platform_runtime")
    def test_generate_missing_passes_providers_and_session(self, mock_runtime, mock_session, mock_service):
        from modules.activities.activity_thumbnail.scheduled_jobs import generate_missing_thumbnails

        db = MagicMock()
        mock_session.return_value.__enter__.return_value = db
        platform = mock_runtime.get_active_platform.return_value

        generate_missing_thumbnails()

        mock_service.generate_missing_activity_thumbnails.assert_called_once_with(
            platform.storage, platform.lock, platform.clock, db
        )

    @patch(f"{MODULE}.activity_thumbnail_service")
    @patch(f"{MODULE}.core_database.SessionLocal")
    @patch(f"{MODULE}.platform_runtime")
    def test_regenerate_all_passes_providers_and_session(self, mock_runtime, mock_session, mock_service):
        from modules.activities.activity_thumbnail.scheduled_jobs import regenerate_all_thumbnails

        db = MagicMock()
        mock_session.return_value.__enter__.return_value = db
        platform = mock_runtime.get_active_platform.return_value

        regenerate_all_thumbnails()

        mock_service.delete_and_regenerate_all_activity_thumbnails.assert_called_once_with(
            platform.storage, platform.lock, platform.clock, db
        )
