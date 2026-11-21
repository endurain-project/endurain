"""The scheduled location backfill, run as the scheduler runs it: the entry point opens its own session."""

import core.scheduler as core_scheduler
import modules.activities.activity.models as activity_models
import modules.activities.activity_geocoding.scheduled_jobs as geocoding_jobs
import modules.activities.activity_streams.constants as stream_constants
from tests._factories.activities import make_activity, make_stream
from tests._factories.users import make_user


def test_the_entry_point_locates_the_gps_activities_that_have_no_place(db, geocoder):
    activity = make_activity(db, make_user(db).id)
    make_stream(db, activity, stream_constants.STREAM_TYPE_MAP, [{"lat": 38.7, "lon": -9.1}])

    geocoding_jobs.run_missing_location_backfill()

    db.expire_all()
    assert db.get(activity_models.Activity, activity.id).city == "Lisbon"


def test_the_recurring_job_runs_hourly_under_the_backfill_lock():
    [job] = geocoding_jobs.recurring_jobs()

    assert job.func is geocoding_jobs.run_missing_location_backfill
    assert (job.minutes, job.lock_name) == (60, geocoding_jobs.BACKFILL_LOCK_NAME)


def test_a_one_shot_pass_is_queued_on_the_scheduler_under_a_fixed_id_and_the_lock():
    job_id = "endurain_backfill_missing_locations_oneshot"
    try:
        geocoding_jobs.schedule_missing_location_backfill()

        job = core_scheduler.scheduler.get_job(job_id)
        assert job.func is core_scheduler.run_locked_job
        assert job.args == (geocoding_jobs.BACKFILL_LOCK_NAME, geocoding_jobs.run_missing_location_backfill)
    finally:
        core_scheduler.scheduler.remove_job(job_id)
