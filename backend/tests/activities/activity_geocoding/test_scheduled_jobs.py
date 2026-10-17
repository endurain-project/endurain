"""Tests for the activity-geocoding scheduled jobs."""

from unittest.mock import MagicMock, patch

_JOBS = "modules.activities.activity_geocoding.scheduled_jobs"


class TestRunMissingLocationBackfill:
    """The scheduled reconciliation net: lock + batched backfill."""

    @patch(f"{_JOBS}.logger")
    @patch(f"{_JOBS}.platform_runtime")
    def test_skips_when_lock_not_acquired(self, mock_runtime, mock_logger):
        from modules.activities.activity_geocoding.scheduled_jobs import run_missing_location_backfill

        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = False
        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value = lock_cm

        run_missing_location_backfill()

        mock_logger.debug.assert_any_call(
            "Geocoding scheduler: another replica holds the backfill lock; skipping",
        )

    @patch(f"{_JOBS}.core_database")
    @patch(f"{_JOBS}.activity_geocoding_service")
    @patch(f"{_JOBS}.platform_runtime")
    def test_runs_backfill_when_acquired(self, mock_runtime, mock_service, mock_db):
        from modules.activities.activity_geocoding.scheduled_jobs import run_missing_location_backfill

        platform = mock_runtime.get_active_platform.return_value
        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = True
        platform.lock.try_acquire.return_value = lock_cm
        mock_service.backfill_missing_activity_locations.return_value = 2

        run_missing_location_backfill()

        mock_service.backfill_missing_activity_locations.assert_called_once_with(
            platform.geocoding, platform.clock, mock_db.SessionLocal.return_value.__enter__.return_value
        )
