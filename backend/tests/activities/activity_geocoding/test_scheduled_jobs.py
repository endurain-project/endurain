"""Tests for the activity-geocoding scheduled jobs."""

from unittest.mock import patch

_JOBS = "modules.activities.activity_geocoding.scheduled_jobs"


class TestRunMissingLocationBackfill:
    """The scheduled reconciliation net: batched backfill under the scheduler's lock."""

    @patch(f"{_JOBS}.core_database")
    @patch(f"{_JOBS}.activity_geocoding_service")
    @patch(f"{_JOBS}.platform_runtime")
    def test_runs_the_backfill(self, mock_runtime, mock_service, mock_db):
        from modules.activities.activity_geocoding.scheduled_jobs import run_missing_location_backfill

        platform = mock_runtime.get_active_platform.return_value

        run_missing_location_backfill()

        mock_service.backfill_missing_activity_locations.assert_called_once_with(
            platform.geocoding, platform.clock, mock_db.SessionLocal.return_value.__enter__.return_value
        )

    def test_the_recurring_job_holds_the_backfill_lock(self):
        from modules.activities.activity_geocoding.scheduled_jobs import BACKFILL_LOCK_NAME, recurring_jobs

        assert [job.lock_name for job in recurring_jobs()] == [BACKFILL_LOCK_NAME]
