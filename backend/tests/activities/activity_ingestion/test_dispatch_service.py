"""The ingestion dispatcher: the one place the deployment profile is read."""

from unittest.mock import MagicMock, patch

import modules.activities.activity_ingestion.dispatch_service as dispatch_service


def _jobs(enabled: bool):
    return patch.object(dispatch_service.core_config.settings, "JOBS_ENABLED", enabled)


class TestCommitOrPublish:
    def test_durable_profile_hands_the_commit_to_the_publisher(self):
        db, publish = MagicMock(), MagicMock()
        with _jobs(True):
            dispatch_service.commit_or_publish(db, publish=publish)

        publish.assert_called_once_with(db.commit)
        db.commit.assert_not_called()

    def test_local_profile_commits_and_publishes_nothing(self):
        db, publish = MagicMock(), MagicMock()
        with _jobs(False):
            dispatch_service.commit_or_publish(db, publish=publish)

        db.commit.assert_called_once()
        publish.assert_not_called()


class TestRunInBackground:
    def test_local_profile_submits_the_job_body(self):
        run = MagicMock()
        with _jobs(False), patch.object(dispatch_service.activity_ingestion_background, "submit") as submit:
            dispatch_service.run_in_background(run, "job", "storage")

        submit.assert_called_once_with(run, "job", "storage")

    def test_durable_profile_leaves_the_job_to_the_worker(self):
        with _jobs(True), patch.object(dispatch_service.activity_ingestion_background, "submit") as submit:
            dispatch_service.run_in_background(MagicMock(), "job")

        submit.assert_not_called()


def test_worker_retries_follows_the_setting():
    with _jobs(True):
        assert dispatch_service.worker_retries() is True
    with _jobs(False):
        assert dispatch_service.worker_retries() is False
