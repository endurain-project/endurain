"""Tests for accepting and running provider refresh jobs."""

from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_ingestion.ingestion_jobs as ingestion_jobs
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


class TestAcceptRefresh:
    def test_publishes_a_durable_event_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.platform_publisher, "publish_committing") as publish,
            patch.object(ingestion_jobs.activity_ingestion_background, "submit_refresh") as submit,
        ):
            result = ingestion_jobs.accept_refresh(7, db)

        assert result == "job-view"
        assert create.call_args.args[2] == activity_ingestion_schema.IngestionJobKind.REFRESH
        # Row and event land in one transaction, so a crash between them cannot
        # leave a job nobody will run.
        assert create.call_args.kwargs["commit"] is False
        assert publish.call_args.kwargs["commit"] == db.commit
        assert publish.call_args.args[1] == {"job_id": create.call_args.args[0]}
        submit.assert_not_called()

    def test_falls_back_to_the_background_pool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.platform_publisher, "publish_committing") as publish,
            patch.object(ingestion_jobs.activity_ingestion_background, "submit_refresh") as submit,
        ):
            ingestion_jobs.accept_refresh(7, db)

        # Same client contract either way — only the executor differs.
        publish.assert_not_called()
        db.commit.assert_called_once()
        submit.assert_called_once_with(create.call_args.args[0])

    def test_a_refresh_job_carries_no_file_fields(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.platform_publisher, "publish_committing"),
        ):
            ingestion_jobs.accept_refresh(7, db)

        assert "filename" not in create.call_args.kwargs
        assert "staged_key" not in create.call_args.kwargs


class TestRunRefreshJob:
    def test_marks_completed_with_the_synced_activity_ids(self):
        synced = [MagicMock(id=11), MagicMock(id=12)]
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=7),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_processing") as processing,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_completed") as completed,
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()

            async def _fake(*_args, **_kwargs):
                return synced

            sync.side_effect = _fake
            ingestion_jobs.run_refresh_job("job-1")

        processing.assert_called_once()
        assert completed.call_args.args[1] == [11, 12]

    def test_the_owner_comes_from_the_row_not_the_event(self):
        """A tampered payload must not make the worker sync somebody else's providers."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=42) as owner,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_processing"),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_completed"),
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()

            async def _fake(user_id, _db):
                assert user_id == 42
                return []

            sync.side_effect = _fake
            ingestion_jobs.run_refresh_job("job-1")

        owner.assert_called_once()

    def test_an_unknown_job_is_a_no_op(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=None),
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_refresh_job("job-1")

        sync.assert_not_called()

    def test_a_provider_failure_is_left_for_the_retry(self):
        """Provider outages and rate limits are exactly what backoff is for."""
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=7),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
            pytest.raises(RuntimeError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()

            async def _fake(*_args, **_kwargs):
                raise RuntimeError("strava is down")

            sync.side_effect = _fake
            ingestion_jobs.run_refresh_job("job-1")

        fail.assert_not_called()

    def test_a_provider_failure_is_terminal_when_nothing_will_retry(self):
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=7),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
            pytest.raises(RuntimeError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()

            async def _fake(*_args, **_kwargs):
                raise RuntimeError("strava is down")

            sync.side_effect = _fake
            ingestion_jobs.run_refresh_job("job-1")

        assert fail.call_args.args[1] == activity_ingestion_schema.IngestionJobErrorCode.PROVIDER_UNAVAILABLE

    def test_a_refresh_that_found_nothing_still_completes(self):
        """Nothing new is a normal outcome, not a failure."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "get_job_owner", return_value=7),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_processing"),
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_completed") as completed,
            patch.object(ingestion_jobs.ingestion_jobs_crud, "mark_failed") as failed,
            patch.object(ingestion_jobs.refresh_entry, "sync_linked_providers") as sync,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()

            async def _fake(*_args, **_kwargs):
                return []

            sync.side_effect = _fake
            ingestion_jobs.run_refresh_job("job-1")

        assert completed.call_args.args[1] == []
        failed.assert_not_called()
