"""The backlog the reprocess migration walks: the activities below the current analysis version."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.migration_service as migration_service
import modules.activities.computation as activities_computation
from tests._factories.activities import make_activity
from tests._factories.reprocess import OLD
from tests._factories.users import make_user

_CURRENT = activities_computation.ANALYSIS_VERSION


def _set(db: Session, activity_id: uuid.UUID, **values: object) -> None:
    db.execute(update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(**values))
    db.commit()


def _row(db: Session, activity_id: uuid.UUID) -> activity_models.Activity:
    db.expire_all()
    return db.execute(select(activity_models.Activity).where(activity_models.Activity.id == activity_id)).scalar_one()


def _activities(db: Session, count: int, **overrides: object) -> list[uuid.UUID]:
    """Store ``count`` activities for one user, each at analysis version 0."""
    user = make_user(db)
    ids = [make_activity(db, user.id, start_time=OLD.replace(day=day), **overrides).id for day in range(1, count + 1)]
    db.commit()
    return ids


class TestListingTheBacklog:
    def test_lists_the_activities_below_the_current_version_in_id_order(self, db):
        ids = _activities(db, 3)
        stamped = _activities(db, 1)[0]
        _set(db, stamped, analysis_version=_CURRENT)

        listed = migration_service.list_activities_to_reprocess(50)

        assert listed == sorted(ids)

    def test_stops_at_the_limit_and_the_next_call_continues_from_what_is_left(self, db):
        ids = sorted(_activities(db, 3))

        first = migration_service.list_activities_to_reprocess(2)
        for activity_id in first:
            migration_service.mark_reprocess_visited(activity_id)

        assert first == ids[:2]
        assert migration_service.list_activities_to_reprocess(2) == ids[2:]

    def test_a_version_above_the_current_one_is_not_listed(self, db):
        [activity_id] = _activities(db, 1)
        _set(db, activity_id, analysis_version=_CURRENT + 1)

        assert migration_service.list_activities_to_reprocess(50) == []

    def test_a_leg_is_listed_like_any_other_activity(self, db):
        user = make_user(db)
        parent = make_activity(db, user.id)
        leg = make_activity(db, user.id, parent_activity_id=parent.id, start_time=OLD)
        db.commit()

        assert set(migration_service.list_activities_to_reprocess(50)) == {parent.id, leg.id}


class TestMarkingAnActivityVisited:
    def test_stamps_the_current_version_and_leaves_the_version_and_updated_at_alone(self, db):
        [activity_id] = _activities(db, 1)
        _set(db, activity_id, updated_at=OLD)
        before = _row(db, activity_id)
        version, updated_at = before.version, before.updated_at

        migration_service.mark_reprocess_visited(activity_id)

        after = _row(db, activity_id)
        assert (after.analysis_version, after.version, after.updated_at) == (_CURRENT, version, updated_at)

    def test_commits_its_own_transaction(self, committed_sessions):
        with committed_sessions() as db:
            [activity_id] = _activities(db, 1)

        migration_service.mark_reprocess_visited(activity_id)

        with committed_sessions() as db:
            assert _row(db, activity_id).analysis_version == _CURRENT

    def test_never_lowers_a_version_above_the_current_one(self, db):
        [activity_id] = _activities(db, 1)
        _set(db, activity_id, analysis_version=_CURRENT + 1)

        migration_service.mark_reprocess_visited(activity_id)

        assert _row(db, activity_id).analysis_version == _CURRENT + 1

    def test_an_unknown_activity_is_not_an_error(self, db):
        migration_service.mark_reprocess_visited(uuid.uuid4())
