"""The scheduled sweep that removes media blobs whose activity is gone, run as the scheduler runs it."""

import dataclasses
import os
import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_media.constants as media_constants
import modules.activities.activity_media.scheduled_jobs as media_jobs

_AREA = media_constants.MEDIA_STORAGE_AREA


def test_the_sweep_removes_an_old_blob_whose_activity_is_gone_and_keeps_a_new_one(tmp_path):
    storage = LocalStorage(str(tmp_path / "plain"), plain_areas=frozenset({_AREA}))
    platform = platform_runtime.get_active_platform()
    platform_runtime.set_active_platform(dataclasses.replace(platform, storage=storage))
    gone = uuid.uuid4()
    storage.save(_AREA, f"{gone}_old.png", b"x")
    storage.save(_AREA, f"{gone}_new.png", b"x")
    old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(tmp_path / "plain" / _AREA / f"{gone}_old.png", (old, old))

    media_jobs.sweep_orphaned_media()

    assert not storage.exists(_AREA, f"{gone}_old.png")
    assert storage.exists(_AREA, f"{gone}_new.png")


def test_a_sweep_with_nothing_to_remove_leaves_the_blobs_alone(tmp_path):
    storage = LocalStorage(str(tmp_path / "plain"), plain_areas=frozenset({_AREA}))
    platform_runtime.set_active_platform(dataclasses.replace(platform_runtime.get_active_platform(), storage=storage))
    storage.save(_AREA, f"{uuid.uuid4()}_new.png", b"x")

    media_jobs.sweep_orphaned_media()

    assert len(list(storage.iter_objects(_AREA))) == 1


def test_the_sweep_runs_daily_under_its_own_lock():
    [job] = media_jobs.recurring_jobs()

    assert job.func is media_jobs.sweep_orphaned_media
    assert (job.minutes, job.lock_name) == (1440, media_jobs.SWEEP_LOCK_NAME)
