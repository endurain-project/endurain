"""The hourly deletion of the Strava data of users who revoked Endurain's access and did not relink in time."""

from datetime import timedelta

from sqlalchemy import select, text

import core.database as core_database
import modules.activities.activity.models as activity_models
import modules.strava.constants as strava_constants
import modules.strava.scheduled_jobs as strava_scheduled_jobs
import modules.users.users_integrations.constants as user_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.activities import make_activity
from tests._factories.users import make_user

_PAST_GRACE = timedelta(days=user_integrations_constants.STRAVA_REVOKED_DATA_GRACE_DAYS + 1)


def _revoked_user_with_an_import(db, *, revoked_ago=_PAST_GRACE):
    user = make_user(db)
    strava_factories.link_strava(db, user.id)
    make_activity(db, user.id, strava_activity_id=1001)
    strava_factories.revoke_strava_access(db, user.id, revoked_ago=revoked_ago)
    return user


def _has_activities(user_id) -> bool:
    with core_database.SessionLocal() as db:
        return bool(
            db.scalars(select(activity_models.Activity.id).where(activity_models.Activity.user_id == user_id)).all()
        )


def _revoked_at(user_id):
    with core_database.SessionLocal() as db:
        return user_integrations_integration.require_user_integrations(user_id, db).strava_revoked_at


def test_the_job_is_registered_under_its_own_lock():
    (job,) = strava_scheduled_jobs.recurring_jobs()

    assert job.func is strava_scheduled_jobs.delete_revoked_data
    assert job.lock_name == strava_scheduled_jobs.REVOKED_DATA_DELETE_LOCK


def test_every_user_past_the_grace_period_is_deleted_page_by_page_and_the_others_are_left(db):
    page = strava_constants.REVOKED_DELETE_PAGE_SIZE
    due = [_revoked_user_with_an_import(db) for _ in range(page + 1)]
    recent = _revoked_user_with_an_import(db, revoked_ago=timedelta(days=1))

    strava_scheduled_jobs.delete_revoked_data()

    assert not any(_has_activities(user.id) for user in due)
    assert all(_revoked_at(user.id) is None for user in due)
    assert _has_activities(recent.id)
    assert _revoked_at(recent.id) is not None


def test_nothing_due_does_nothing(db):
    recent = _revoked_user_with_an_import(db, revoked_ago=timedelta(days=1))

    strava_scheduled_jobs.delete_revoked_data()

    assert _has_activities(recent.id)


def test_a_user_whose_deletion_fails_is_left_marked_and_the_rest_still_run(committed_sessions):
    with committed_sessions() as db:
        failing = _revoked_user_with_an_import(db)
        other = _revoked_user_with_an_import(db)
        # The database refuses the notice that closes the deletion of one user, as a real failure would.
        db.execute(
            text(
                "CREATE FUNCTION refuse_notice() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                f"IF NEW.user_id = '{failing.id}' THEN RAISE EXCEPTION 'refused'; END IF; RETURN NEW; END $$"
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER refuse_notice BEFORE INSERT ON notifications "
                "FOR EACH ROW EXECUTE FUNCTION refuse_notice()"
            )
        )
        db.commit()

    strava_scheduled_jobs.delete_revoked_data()

    assert _revoked_at(failing.id) is not None, "left marked so the next run tries again"
    assert _revoked_at(other.id) is None
    assert not _has_activities(other.id)
