"""What changed and what was deleted, per health kind, on the real database.

Every health record carries an ``updated_at`` the database stamps; a deleted one leaves a tombstone. The sync
integration functions page both in ``(stamp, id)`` order for the owner only.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

import modules.health.health_fasting.crud as fasting_crud
import modules.health.health_fasting.integration_service as fasting_integration
import modules.health.health_poop.crud as poop_crud
import modules.health.health_poop.integration_service as poop_integration
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.integration_service as steps_integration
import modules.health.health_targets.integration_service as targets_integration
import modules.health.health_targets.models as targets_models
import modules.health.health_water.crud as water_crud
import modules.health.health_water.integration_service as water_integration
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.integration_service as weight_integration
import modules.health.health_weight.models as weight_models
import modules.health.models as health_models
import modules.health.record_crud as health_record_crud
import modules.health.scheduled_jobs as health_scheduled_jobs
from tests._factories import health as health_factories
from tests._factories.users import make_user

_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
_OLD = datetime(2020, 1, 1, tzinfo=UTC)
_MIDDLE = datetime(2021, 1, 1, tzinfo=UTC)


def _on(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def _weight(db, user_id, day):
    return health_factories.make_health_weight(db, user_id, date=date(2024, 1, day))


def _steps(db, user_id, day):
    return health_factories.make_health_steps(db, user_id, date=date(2024, 1, day))


def _sleep(db, user_id, day):
    return health_factories.make_health_sleep(
        db,
        user_id,
        date=date(2024, 1, day),
        sleep_stages=[
            {"stage_type": "deep", "start_time_gmt": _on(day), "end_time_gmt": _on(day) + timedelta(hours=1)}
        ],
    )


def _water(db, user_id, day):
    return health_factories.make_health_water(db, user_id, date=date(2024, 1, day))


def _poop(db, user_id, day):
    return health_factories.make_health_poop(db, user_id, date_time=_on(day))


def _fasting(db, user_id, day):
    return health_factories.make_health_fasting(
        db, user_id, fast_start_time=_on(day), fast_end_time=_on(day) + timedelta(hours=10), status="completed"
    )


# (sync type, stage a row, crud spec, list_changed, list_deletions)
_KINDS = [
    (
        "health_weight",
        _weight,
        weight_crud.SPEC,
        weight_integration.list_changed_health_weight,
        weight_integration.list_health_weight_deletions,
    ),
    (
        "health_steps",
        _steps,
        steps_crud.SPEC,
        steps_integration.list_changed_health_steps,
        steps_integration.list_health_steps_deletions,
    ),
    (
        "health_sleep",
        _sleep,
        sleep_crud.SPEC,
        sleep_integration.list_changed_health_sleep,
        sleep_integration.list_health_sleep_deletions,
    ),
    (
        "health_water",
        _water,
        water_crud.SPEC,
        water_integration.list_changed_health_water,
        water_integration.list_health_water_deletions,
    ),
    (
        "health_poop",
        _poop,
        poop_crud.SPEC,
        poop_integration.list_changed_health_poop,
        poop_integration.list_health_poop_deletions,
    ),
    (
        "health_fasting",
        _fasting,
        fasting_crud.SPEC,
        fasting_integration.list_changed_health_fasting,
        fasting_integration.list_health_fasting_deletions,
    ),
]
_IDS = [kind[0] for kind in _KINDS]
_PARAMS = ("sync_type", "make", "spec", "changed", "deletions")


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


def _stamp(db, model, row_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(sa.update(model).where(model.id == row_id).values(updated_at=stamp))
    db.flush()


@pytest.mark.parametrize(_PARAMS, _KINDS, ids=_IDS)
class TestUpdatedAt:
    def test_an_insert_stamps_the_row(self, db, user, sync_type, make, spec, changed, deletions):
        record = make(db, user.id, 1)

        assert db.get(spec.model, record.id).updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(
        self, db, user, sync_type, make, spec, changed, deletions
    ):
        record = make(db, user.id, 1)
        _stamp(db, spec.model, record.id, _OLD)

        db.execute(sa.update(spec.model).where(spec.model.id == record.id).values(source="garmin"))
        db.expire_all()

        assert db.get(spec.model, record.id).updated_at > _OLD

    def test_an_orm_edit_moves_the_stamp(self, db, user, sync_type, make, spec, changed, deletions):
        record = make(db, user.id, 1)
        _stamp(db, spec.model, record.id, _OLD)
        db.expire_all()

        row = db.get(spec.model, record.id)
        row.source = "garmin"
        db.flush()
        db.refresh(row)

        assert row.updated_at > _OLD


@pytest.mark.parametrize(_PARAMS, _KINDS, ids=_IDS)
class TestListChanged:
    def _seed(self, db, user, other, make, spec):
        """Stamp three records of the user (two old, one older than the last) and one of another user."""
        rows = [make(db, user.id, 1), make(db, user.id, 2), make(db, user.id, 3), make(db, other.id, 4)]
        rows[:2] = sorted(rows[:2], key=lambda row: row.id)
        for row in rows[:2]:
            _stamp(db, spec.model, row.id, _OLD)
        _stamp(db, spec.model, rows[2].id, _MIDDLE)
        _stamp(db, spec.model, rows[3].id, _OLD)
        return rows

    def test_pages_in_stamp_then_id_order_for_the_owner_only(
        self, db, user, other, sync_type, make, spec, changed, deletions
    ):
        rows = self._seed(db, user, other, make, spec)

        result = changed(user.id, None, _FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [rows[0].id, rows[1].id, rows[2].id]
        assert all(r.updated_at is not None for r in result)

    def test_after_is_exclusive_and_ties_break_on_id(self, db, user, other, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, user, other, make, spec)

        result = changed(user.id, (_OLD, rows[0].id), _FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [rows[1].id, rows[2].id]

    def test_until_is_an_exclusive_bound(self, db, user, other, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, user, other, make, spec)

        result = changed(user.id, None, _MIDDLE, 10, db)

        assert [r.id for r in result] == [rows[0].id, rows[1].id]

    def test_limit_caps_the_page(self, db, user, other, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, user, other, make, spec)

        assert [r.id for r in changed(user.id, None, _FAR_FUTURE, 1, db)] == [rows[0].id]


class TestSleepChangedCarriesStages:
    def test_the_full_read_with_stages_is_returned(self, db, user):
        _sleep(db, user.id, 1)

        result = sleep_integration.list_changed_health_sleep(user.id, None, _FAR_FUTURE, 10, db)

        assert isinstance(result[0], sleep_schema.HealthSleepRead)
        assert result[0].sleep_stages


def _targets(db, user):
    """The empty targets every new user starts with."""
    return db.scalars(
        sa.select(targets_models.HealthTargets).where(targets_models.HealthTargets.user_id == user.id)
    ).one()


class TestTargets:
    def test_targets_are_listed_when_changed(self, db, user):
        row = _targets(db, user)

        result = targets_integration.list_changed_health_targets(user.id, None, _FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [row.id]
        assert result[0].updated_at is not None

    def test_a_core_update_moves_the_stamp(self, db, user):
        row = _targets(db, user)
        _stamp(db, targets_models.HealthTargets, row.id, _OLD)

        db.execute(
            sa.update(targets_models.HealthTargets).where(targets_models.HealthTargets.id == row.id).values(steps=5)
        )
        db.expire_all()

        assert db.get(targets_models.HealthTargets, row.id).updated_at > _OLD

    def test_no_deletions_are_listed(self, db, user):
        assert targets_integration.list_health_targets_deletions(user.id, None, _FAR_FUTURE, 10, db) == []


class TestBmiRecalculation:
    def test_the_bulk_update_moves_the_stamp(self, db, user):
        record = _weight(db, user.id, 1)
        _stamp(db, weight_models.HealthWeight, record.id, _OLD)

        weight_integration.recalculate_bmi_for_user(user.id, 180.0, db)
        db.expire_all()

        assert db.get(weight_models.HealthWeight, record.id).updated_at > _OLD


@pytest.mark.parametrize(_PARAMS, _KINDS, ids=_IDS)
class TestDeletions:
    def test_a_delete_records_a_tombstone_of_its_type(self, db, user, sync_type, make, spec, changed, deletions):
        record_id = make(db, user.id, 1).id

        health_record_crud.delete(spec, record_id, user.id, db, if_match='"1"')

        result = deletions(user.id, None, _FAR_FUTURE, 10, db)
        assert [(d.type, d.record_id) for d in result] == [(sync_type, record_id)]
        assert result[0].position == (result[0].deleted_at, db.scalar(sa.select(health_models.HealthRecordDeletion.id)))

    def test_other_types_and_owners_are_not_listed(self, db, user, other, sync_type, make, spec, changed, deletions):
        db.add_all(
            [
                health_models.HealthRecordDeletion(user_id=user.id, record_id=uuid.uuid4(), record_type="other_type"),
                health_models.HealthRecordDeletion(user_id=other.id, record_id=uuid.uuid4(), record_type=sync_type),
            ]
        )
        db.flush()

        assert deletions(user.id, None, _FAR_FUTURE, 10, db) == []

    def test_pages_in_stamp_then_id_order(self, db, user, sync_type, make, spec, changed, deletions):
        ids = [uuid.uuid4() for _ in range(3)]
        old_a, old_b = (
            health_models.HealthRecordDeletion(
                id=uuid.UUID(int=n), user_id=user.id, record_id=ids[n - 1], record_type=sync_type, deleted_at=_OLD
            )
            for n in (1, 2)
        )
        newer = health_models.HealthRecordDeletion(
            id=uuid.UUID(int=3), user_id=user.id, record_id=ids[2], record_type=sync_type, deleted_at=_MIDDLE
        )
        db.add_all([newer, old_a, old_b])
        db.flush()

        everything = deletions(user.id, None, _FAR_FUTURE, 10, db)
        after_first = deletions(user.id, everything[0].position, _FAR_FUTURE, 10, db)
        before_middle = deletions(user.id, None, _MIDDLE, 10, db)
        limited = deletions(user.id, None, _FAR_FUTURE, 2, db)

        assert [d.record_id for d in everything] == ids
        assert [d.record_id for d in after_first] == ids[1:]
        assert [d.record_id for d in before_middle] == ids[:2]
        assert [d.record_id for d in limited] == ids[:2]


class TestPruneJob:
    def test_the_daily_job_removes_the_tombstones_past_their_retention(self, committed_sessions):
        recent = uuid.uuid4()
        with committed_sessions() as db:
            user = make_user(db)
            db.add_all(
                [
                    health_models.HealthRecordDeletion(
                        user_id=user.id, record_id=uuid.uuid4(), record_type="health_weight", deleted_at=_OLD
                    ),
                    health_models.HealthRecordDeletion(user_id=user.id, record_id=recent, record_type="health_weight"),
                ]
            )
            db.commit()

        (job,) = health_scheduled_jobs.recurring_jobs()
        assert job.lock_name == health_scheduled_jobs.PRUNE_LOCK_NAME
        job.func()

        with committed_sessions() as db:
            assert [d.record_id for d in db.scalars(sa.select(health_models.HealthRecordDeletion))] == [recent]
