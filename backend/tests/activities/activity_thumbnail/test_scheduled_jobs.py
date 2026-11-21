"""The scheduled thumbnail work, run as the scheduler runs it: the entry points open their own session."""

import dataclasses
import os
import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest
from jasil.backends.storage_local import LocalStorage

import core.scheduler as core_scheduler
import modules.activities.activity.models as activity_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_thumbnail.constants as thumbnail_constants
import modules.activities.activity_thumbnail.scheduled_jobs as thumbnail_jobs
from tests._factories.activities import make_activity, make_stream
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_AREA = thumbnail_constants.THUMBNAIL_STORAGE_AREA
_ROUTE = [{"lat": 38.70, "lon": -9.10}, {"lat": 38.72, "lon": -9.14}]


@pytest.fixture
def routed(db, tile_server):
    edit_server_settings(db, tileserver_url=tile_server.url())
    activity = make_activity(db, make_user(db).id)
    make_stream(db, activity, stream_constants.STREAM_TYPE_MAP, _ROUTE)
    return activity


def _key_of(db, activity) -> str | None:
    db.expire_all()
    return db.get(activity_models.Activity, activity.id).map_thumbnail_path


def test_the_backfill_entry_point_renders_the_thumbnails_that_are_missing(db, routed):
    thumbnail_jobs.generate_missing_thumbnails()

    assert _key_of(db, routed) == f"{routed.id}.webp"


def test_the_regeneration_entry_point_renders_every_thumbnail_again(db, routed):
    platform_runtime.get_active_platform().storage.save(_AREA, f"{routed.id}.webp", b"stale")

    thumbnail_jobs.regenerate_all_thumbnails()

    assert _key_of(db, routed) == f"{routed.id}.webp"
    assert platform_runtime.get_active_platform().storage.get(_AREA, f"{routed.id}.webp") != b"stale"


def test_the_sweep_entry_point_removes_an_old_thumbnail_whose_activity_is_gone(tmp_path):
    storage = LocalStorage(str(tmp_path / "plain"), plain_areas=frozenset({_AREA}))
    platform_runtime.set_active_platform(dataclasses.replace(platform_runtime.get_active_platform(), storage=storage))
    gone = f"{uuid.uuid4()}.webp"
    storage.save(_AREA, gone, b"x")
    old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(tmp_path / "plain" / _AREA / gone, (old, old))

    thumbnail_jobs.sweep_orphaned_thumbnails()

    assert not storage.exists(_AREA, gone)


def test_the_recurring_jobs_are_the_hourly_backfill_and_the_daily_sweep_under_their_own_locks():
    jobs = {job.func: job for job in thumbnail_jobs.recurring_jobs()}

    backfill = jobs[thumbnail_jobs.generate_missing_thumbnails]
    sweep = jobs[thumbnail_jobs.sweep_orphaned_thumbnails]
    assert (backfill.minutes, backfill.lock_name) == (60, thumbnail_jobs.BACKFILL_LOCK_NAME)
    assert (sweep.minutes, sweep.lock_name) == (1440, thumbnail_jobs.SWEEP_LOCK_NAME)


@pytest.mark.parametrize(
    ("schedule", "job_id", "func"),
    [
        (
            thumbnail_jobs.schedule_missing_thumbnail_generation,
            "endurain_generate_missing_thumbnails_oneshot",
            core_scheduler.run_locked_job,
        ),
        (
            thumbnail_jobs.schedule_full_thumbnail_regeneration,
            "endurain_regenerate_all_thumbnails",
            thumbnail_jobs.regenerate_all_thumbnails,
        ),
    ],
)
def test_a_one_shot_pass_is_queued_on_the_scheduler_under_a_fixed_id(schedule, job_id, func):
    try:
        schedule()

        assert core_scheduler.scheduler.get_job(job_id).func is func
    finally:
        core_scheduler.scheduler.remove_job(job_id)
