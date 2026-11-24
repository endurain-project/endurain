"""Scheduled work owned by users, run through its scheduler entry points on the real database."""

import os
import time
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import core.blob_sweep as core_blob_sweep
import core.config as core_config
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.events as users_events
import modules.users.users.models as users_models
import modules.users.users.scheduled_jobs as users_scheduled_jobs
from tests._factories.users import make_user


class TestRecurringJobs:
    def test_each_job_holds_its_own_distributed_lock_and_runs_at_its_interval(self):
        jobs = {job.func.__name__: job for job in users_scheduled_jobs.recurring_jobs()}

        assert set(jobs) == {"requeue_stalled_deletions", "sweep_unreferenced_photos"}
        assert jobs["requeue_stalled_deletions"].lock_name == users_scheduled_jobs.DELETION_SWEEP_LOCK_NAME
        assert jobs["sweep_unreferenced_photos"].lock_name == users_scheduled_jobs.PHOTO_SWEEP_LOCK_NAME
        assert users_scheduled_jobs.DELETION_SWEEP_LOCK_NAME != users_scheduled_jobs.PHOTO_SWEEP_LOCK_NAME
        assert jobs["requeue_stalled_deletions"].minutes == users_constants.DELETION_SWEEP_INTERVAL_MINUTES
        assert jobs["sweep_unreferenced_photos"].minutes == users_constants.PHOTO_SWEEP_INTERVAL_MINUTES


class TestEntryPoints:
    def test_the_deletion_sweep_queues_a_stalled_deletion_again_with_the_providers_it_resolves(
        self, committed_sessions, monkeypatch, _publish_local_platform
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        published: list = []
        _publish_local_platform.events.subscribe(users_events.USERS_DELETION_REQUESTED, published.append)
        with committed_sessions() as db:
            user = make_user(db)
            users_crud.stage_deletion_request(user.id, db)
            db.execute(
                sa.update(users_models.Users)
                .where(users_models.Users.id == user.id)
                .values(deletion_requested_at=datetime.now(UTC) - timedelta(hours=5))
            )
            db.commit()

        users_scheduled_jobs.requeue_stalled_deletions()

        [event] = published
        assert event.payload["user_id"] == str(user.id)

    def test_the_photo_sweep_removes_an_old_photo_no_user_names(
        self, committed_sessions, tmp_path, _publish_local_platform
    ):
        storage = _publish_local_platform.storage
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        orphan = f"{user.id}.png"
        storage.save(users_constants.USER_IMAGE_STORAGE_AREA, orphan, b"x", "image/png")
        old = time.time() - 2 * core_blob_sweep.MIN_AGE_SECONDS
        for path in tmp_path.rglob("*"):
            if path.is_file():
                os.utime(path, (old, old))

        users_scheduled_jobs.sweep_unreferenced_photos()

        assert list(storage.list_keys(users_constants.USER_IMAGE_STORAGE_AREA)) == []
