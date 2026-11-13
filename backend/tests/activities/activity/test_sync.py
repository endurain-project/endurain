"""Incremental sync of activities: ``updated_at``, tombstones, the change surfaces and the prune job."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from tests._helpers.db import create_sqlite_session

import core.sync as core_sync
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.scheduled_jobs as activity_scheduled_jobs
import modules.activities.activity.schema as activity_schema

_USER_1 = uuid.UUID(int=1)
_USER_2 = uuid.UUID(int=2)

_FAR_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()


def _activity(user_id: uuid.UUID = _USER_1, **overrides) -> activity_models.Activity:
    values = {
        "user_id": user_id,
        "name": "Run",
        "distance": 1000,
        "activity_type": 1,
        "start_time": datetime(2026, 1, 1, 9, tzinfo=UTC),
        "end_time": datetime(2026, 1, 1, 10, tzinfo=UTC),
        "timezone": "UTC",
        "total_elapsed_time": 3600,
        "total_timer_time": 3500,
        "visibility": 2,
        "is_hidden": False,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        **{
            flag: False
            for flag in (
                "hide_start_time",
                "hide_location",
                "hide_map",
                "hide_hr",
                "hide_power",
                "hide_cadence",
                "hide_elevation",
                "hide_speed",
                "hide_pace",
                "hide_laps",
                "hide_workout_sets_steps",
                "hide_gear",
            )
        },
    }
    values.update(overrides)
    return activity_models.Activity(**values)


def _stamp(db, activity_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(
        update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(updated_at=stamp)
    )


def _add(db, **overrides) -> uuid.UUID:
    activity = _activity(**overrides)
    db.add(activity)
    db.flush()
    return activity.id


class TestUpdatedAt:
    def test_an_insert_is_stamped(self, db):
        activity_id = _add(db)
        db.commit()

        assert db.get(activity_models.Activity, activity_id).updated_at is not None

    def test_an_orm_edit_restamps(self, db):
        activity_id = _add(db)
        _stamp(db, activity_id, datetime(2020, 1, 1))
        db.commit()
        db.expire_all()

        db.get(activity_models.Activity, activity_id).name = "Renamed"
        db.commit()
        db.expire_all()

        assert db.get(activity_models.Activity, activity_id).updated_at.year > 2020

    def test_a_core_update_restamps_without_bumping_the_version(self, db):
        activity_id = _add(db)
        _stamp(db, activity_id, datetime(2020, 1, 1))
        db.commit()
        version = db.get(activity_models.Activity, activity_id).version

        activity_crud.set_activity_thumbnail_key(activity_id, "1.webp", db)
        db.commit()
        db.expire_all()

        row = db.get(activity_models.Activity, activity_id)
        assert row.updated_at.year > 2020
        assert row.version == version

    def test_touch_activity_restamps_without_bumping_the_version(self, db):
        activity_id = _add(db)
        _stamp(db, activity_id, datetime(2020, 1, 1))
        db.commit()
        version = db.get(activity_models.Activity, activity_id).version

        activity_integration.touch_activity(activity_id, db)
        db.commit()
        db.expire_all()

        row = db.get(activity_models.Activity, activity_id)
        assert row.updated_at.year > 2020
        assert row.version == version

    def test_the_write_schemas_do_not_accept_it(self):
        import modules.activities.activity.contracts as activity_contracts

        assert "updated_at" not in activity_contracts.ActivityCore.model_fields
        assert "updated_at" not in activity_schema.ActivityEdit.model_fields
        assert "updated_at" in activity_schema.ActivityRead.model_fields
        assert "updated_at" in activity_schema.ActivitySummaryRead.model_fields


class TestTombstones:
    def _tombstones(self, db) -> list[tuple[uuid.UUID, uuid.UUID]]:
        rows = db.query(activity_models.ActivityDeletion).order_by(activity_models.ActivityDeletion.record_id).all()
        return [(row.user_id, row.record_id) for row in rows]

    def test_the_single_delete_records_one(self, db):
        activity_id = _add(db)
        version = db.get(activity_models.Activity, activity_id).version
        db.commit()

        activity_crud.delete_activity(activity_id, _USER_1, db, if_match=f'"{version}"')
        db.commit()

        assert self._tombstones(db) == [(_USER_1, activity_id)]

    def test_the_strava_batch_delete_records_the_deleted_ids_only(self, db):
        strava = [
            _add(db, strava_activity_id=100 + n, start_time=datetime(2026, 2, 1 + n, tzinfo=UTC)) for n in range(2)
        ]
        _add(db, start_time=datetime(2026, 3, 1, tzinfo=UTC))
        db.commit()

        deleted = activity_crud.delete_all_strava_activities_for_user(_USER_1, db, limit=10)
        db.commit()

        assert sorted(deleted) == sorted(strava)
        assert self._tombstones(db) == [(_USER_1, strava_id) for strava_id in sorted(strava)]

    def test_the_account_batch_delete_records_them(self, db):
        ids = [_add(db, start_time=datetime(2026, 2, 1 + n, tzinfo=UTC)) for n in range(3)]
        db.commit()

        deleted = activity_crud.delete_activities_batch_for_user(_USER_1, 10, db)
        db.commit()

        assert sorted(deleted) == sorted(ids)
        assert sorted(record for _, record in self._tombstones(db)) == sorted(ids)


class TestSurfaces:
    def test_changed_activities_page_in_stamp_then_id_order_with_ties(self, db):
        tied_a, tied_b, third, other = (_add(db, start_time=datetime(2026, 1, 1 + n, tzinfo=UTC)) for n in range(4))
        first, second = sorted((tied_a, tied_b))
        db.execute(update(activity_models.Activity).where(activity_models.Activity.id == other).values(user_id=_USER_2))
        _stamp(db, first, datetime(2026, 5, 1))
        _stamp(db, second, datetime(2026, 5, 1))
        _stamp(db, third, datetime(2026, 5, 2))
        db.commit()

        page = activity_integration.list_changed_activities(_USER_1, None, _FAR_FUTURE, 2, db)
        assert [a.id for a in page] == [first, second]
        assert all(a.updated_at is not None for a in page)

        rest = activity_integration.list_changed_activities(
            _USER_1, (page[-1].updated_at, page[-1].id), _FAR_FUTURE, 10, db
        )
        assert [a.id for a in rest] == [third]

    def test_after_is_exclusive_and_until_bounds_the_stamp(self, db):
        first, second = (_add(db, start_time=datetime(2026, 1, 1 + n, tzinfo=UTC)) for n in range(2))
        _stamp(db, first, datetime(2026, 5, 1))
        _stamp(db, second, datetime(2026, 5, 3))
        db.commit()

        bounded = activity_integration.list_changed_activities(_USER_1, None, datetime(2026, 5, 3, tzinfo=UTC), 10, db)
        assert [a.id for a in bounded] == [first]

        after = activity_integration.list_changed_activities(
            _USER_1, (datetime(2026, 5, 1, tzinfo=UTC), first), _FAR_FUTURE, 10, db
        )
        assert [a.id for a in after] == [second]

    def test_deletions_page_in_order_and_belong_to_the_owner(self, db):
        seven, eight, nine, ten = (uuid.uuid4() for _ in range(4))
        db.add_all(
            [
                activity_models.ActivityDeletion(user_id=_USER_1, record_id=seven, deleted_at=datetime(2026, 5, 1)),
                activity_models.ActivityDeletion(user_id=_USER_1, record_id=eight, deleted_at=datetime(2026, 5, 2)),
                activity_models.ActivityDeletion(user_id=_USER_1, record_id=nine, deleted_at=datetime(2026, 5, 3)),
                activity_models.ActivityDeletion(user_id=_USER_2, record_id=ten, deleted_at=datetime(2026, 5, 1)),
            ]
        )
        db.commit()

        page = activity_integration.list_activity_deletions(_USER_1, None, _FAR_FUTURE, 2, db)
        assert [d.record_id for d in page] == [seven, eight]
        assert {d.type for d in page} == {"activity"}
        assert page[0].position[0] == page[0].deleted_at
        assert all(isinstance(d.position[1], uuid.UUID) for d in page)

        rest = activity_integration.list_activity_deletions(_USER_1, page[-1].position, _FAR_FUTURE, 10, db)
        assert [d.record_id for d in rest] == [nine]


class TestPrune:
    def test_removes_only_old_tombstones(self, db, monkeypatch):
        now = datetime.now(UTC)
        old_record, recent_record = uuid.uuid4(), uuid.uuid4()
        db.add_all(
            [
                activity_models.ActivityDeletion(
                    user_id=_USER_1,
                    record_id=old_record,
                    deleted_at=now - core_sync.TOMBSTONE_RETENTION - timedelta(days=1),
                ),
                activity_models.ActivityDeletion(
                    user_id=_USER_1, record_id=recent_record, deleted_at=now - timedelta(days=1)
                ),
            ]
        )
        db.commit()

        class _Scope:
            def __enter__(self):
                return db

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(activity_scheduled_jobs.core_database, "SessionLocal", lambda: _Scope())

        activity_scheduled_jobs.prune_activity_deletions()

        assert [row.record_id for row in db.query(activity_models.ActivityDeletion).all()] == [recent_record]

    def test_the_job_is_scheduled_daily(self):
        (job,) = activity_scheduled_jobs.recurring_jobs()
        assert job.func is activity_scheduled_jobs.prune_activity_deletions
