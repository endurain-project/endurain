from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from tests._helpers.db import create_sqlite_session

import modules.health.health_fasting.crud as fasting_crud
import modules.health.health_fasting.integration_service as fasting_integration
import modules.health.health_fasting.models as fasting_models
import modules.health.health_poop.crud as poop_crud
import modules.health.health_poop.integration_service as poop_integration
import modules.health.health_poop.models as poop_models
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_sleep.models as sleep_models
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.integration_service as steps_integration
import modules.health.health_steps.models as steps_models
import modules.health.health_targets.integration_service as targets_integration
import modules.health.health_targets.models as targets_models
import modules.health.health_water.crud as water_crud
import modules.health.health_water.integration_service as water_integration
import modules.health.health_water.models as water_models
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.integration_service as weight_integration
import modules.health.health_weight.models as weight_models
import modules.health.models as health_models
import modules.health.record_crud as health_record_crud
import modules.health.scheduled_jobs as health_scheduled_jobs

FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
OLD = datetime(2020, 1, 1)
MIDDLE = datetime(2021, 1, 1)
USER = 1
OTHER_USER = 2


def _weight(day: int, user_id: int = USER):
    return weight_models.HealthWeight(user_id=user_id, date=date(2024, 1, day), weight_kg=Decimal("70.5"))


def _steps(day: int, user_id: int = USER):
    return steps_models.HealthSteps(user_id=user_id, date=date(2024, 1, day), steps=100)


def _sleep(day: int, user_id: int = USER):
    return sleep_models.HealthSleep(
        user_id=user_id, date=date(2024, 1, day), sleep_stages=[{"stage_type": "deep", "duration_seconds": 60}]
    )


def _water(day: int, user_id: int = USER):
    return water_models.HealthWater(user_id=user_id, date=date(2024, 1, day), amount_ml=Decimal("250"))


def _poop(day: int, user_id: int = USER):
    return poop_models.HealthPoop(user_id=user_id, date_time=datetime(2024, 1, day, tzinfo=UTC))


def _fasting(day: int, user_id: int = USER):
    return fasting_models.HealthFasting(
        user_id=user_id, fast_start_time=datetime(2024, 1, day, tzinfo=UTC), status="completed"
    )


# (sync type, row factory, crud spec, list_changed, list_deletions)
KINDS = [
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
IDS = [kind[0] for kind in KINDS]


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _stamp(db, model, row_id: int, stamp: datetime) -> None:
    db.execute(update(model).where(model.id == row_id).values(updated_at=stamp))
    db.flush()


@pytest.mark.parametrize(("sync_type", "make", "spec", "changed", "deletions"), KINDS, ids=IDS)
class TestUpdatedAt:
    def test_an_insert_stamps_the_row(self, db, sync_type, make, spec, changed, deletions):
        row = make(1)
        db.add(row)
        db.flush()
        db.refresh(row)

        assert row.updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(self, db, sync_type, make, spec, changed, deletions):
        row = make(1)
        db.add(row)
        db.flush()
        _stamp(db, spec.model, row.id, OLD)

        db.execute(update(spec.model).where(spec.model.id == row.id).values(source="garmin"))
        db.expire_all()

        assert db.get(spec.model, row.id).updated_at > OLD

    def test_an_orm_edit_moves_the_stamp(self, db, sync_type, make, spec, changed, deletions):
        row = make(1)
        db.add(row)
        db.flush()
        _stamp(db, spec.model, row.id, OLD)
        db.expire_all()

        row = db.get(spec.model, row.id)
        row.source = "garmin"
        db.flush()
        db.refresh(row)

        assert row.updated_at > OLD


@pytest.mark.parametrize(("sync_type", "make", "spec", "changed", "deletions"), KINDS, ids=IDS)
class TestListChanged:
    def _seed(self, db, make, spec):
        rows = [make(1), make(2), make(3), make(4, OTHER_USER)]
        db.add_all(rows)
        db.flush()
        for row in rows[:2]:
            _stamp(db, spec.model, row.id, OLD)
        _stamp(db, spec.model, rows[2].id, MIDDLE)
        _stamp(db, spec.model, rows[3].id, OLD)
        return rows

    def test_pages_in_stamp_then_id_order_for_the_owner_only(self, db, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, make, spec)

        result = changed(USER, None, FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [rows[0].id, rows[1].id, rows[2].id]
        assert all(r.updated_at is not None for r in result)

    def test_after_is_exclusive_and_ties_break_on_id(self, db, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, make, spec)

        result = changed(USER, (OLD.replace(tzinfo=None), rows[0].id), FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [rows[1].id, rows[2].id]

    def test_until_is_an_exclusive_bound(self, db, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, make, spec)

        result = changed(USER, None, MIDDLE, 10, db)

        assert [r.id for r in result] == [rows[0].id, rows[1].id]

    def test_limit_caps_the_page(self, db, sync_type, make, spec, changed, deletions):
        rows = self._seed(db, make, spec)

        assert [r.id for r in changed(USER, None, FAR_FUTURE, 1, db)] == [rows[0].id]


class TestSleepChangedCarriesStages:
    def test_the_full_read_with_stages_is_returned(self, db):
        row = _sleep(1)
        db.add(row)
        db.flush()

        result = sleep_integration.list_changed_health_sleep(USER, None, FAR_FUTURE, 10, db)

        assert isinstance(result[0], sleep_schema.HealthSleepRead)
        assert result[0].sleep_stages


class TestTargets:
    def test_targets_are_listed_when_changed(self, db):
        row = targets_models.HealthTargets(user_id=USER)
        db.add(row)
        db.flush()

        result = targets_integration.list_changed_health_targets(USER, None, FAR_FUTURE, 10, db)

        assert [r.id for r in result] == [row.id]
        assert result[0].updated_at is not None

    def test_a_core_update_moves_the_stamp(self, db):
        row = targets_models.HealthTargets(user_id=USER)
        db.add(row)
        db.flush()
        _stamp(db, targets_models.HealthTargets, row.id, OLD)

        db.execute(
            update(targets_models.HealthTargets).where(targets_models.HealthTargets.id == row.id).values(steps=5)
        )
        db.expire_all()

        assert db.get(targets_models.HealthTargets, row.id).updated_at > OLD

    def test_no_deletions_are_listed(self, db):
        assert targets_integration.list_health_targets_deletions(USER, None, FAR_FUTURE, 10, db) == []


class TestBmiRecalculation:
    def test_the_bulk_update_moves_the_stamp(self, db):
        row = _weight(1)
        db.add(row)
        db.flush()
        _stamp(db, weight_models.HealthWeight, row.id, OLD)

        weight_integration.recalculate_bmi_for_user(USER, 180.0, db)
        db.expire_all()

        assert db.get(weight_models.HealthWeight, row.id).updated_at > OLD


@pytest.mark.parametrize(("sync_type", "make", "spec", "changed", "deletions"), KINDS, ids=IDS)
class TestDeletions:
    def test_a_delete_records_a_tombstone_of_its_type(self, db, sync_type, make, spec, changed, deletions):
        row = make(1)
        db.add(row)
        db.flush()
        row_id = row.id

        health_record_crud.delete(spec, row_id, USER, db, if_match="*")

        result = deletions(USER, None, FAR_FUTURE, 10, db)
        assert [(d.type, d.record_id) for d in result] == [(sync_type, row_id)]
        assert result[0].position == (result[0].deleted_at, db.scalar(select(health_models.HealthRecordDeletion.id)))

    def test_other_types_and_owners_are_not_listed(self, db, sync_type, make, spec, changed, deletions):
        db.add_all(
            [
                health_models.HealthRecordDeletion(user_id=USER, record_id=1, record_type="other_type"),
                health_models.HealthRecordDeletion(user_id=OTHER_USER, record_id=2, record_type=sync_type),
            ]
        )
        db.flush()

        assert deletions(USER, None, FAR_FUTURE, 10, db) == []

    def test_pages_in_stamp_then_id_order(self, db, sync_type, make, spec, changed, deletions):
        old_a = health_models.HealthRecordDeletion(user_id=USER, record_id=10, record_type=sync_type, deleted_at=OLD)
        old_b = health_models.HealthRecordDeletion(user_id=USER, record_id=11, record_type=sync_type, deleted_at=OLD)
        newer = health_models.HealthRecordDeletion(user_id=USER, record_id=12, record_type=sync_type, deleted_at=MIDDLE)
        db.add_all([newer, old_a, old_b])
        db.flush()

        everything = deletions(USER, None, FAR_FUTURE, 10, db)
        after_first = deletions(USER, everything[0].position, FAR_FUTURE, 10, db)
        before_middle = deletions(USER, None, MIDDLE, 10, db)
        limited = deletions(USER, None, FAR_FUTURE, 2, db)

        assert [d.record_id for d in everything] == [10, 11, 12]
        assert [d.record_id for d in after_first] == [11, 12]
        assert [d.record_id for d in before_middle] == [10, 11]
        assert [d.record_id for d in limited] == [10, 11]


class TestPrune:
    def test_removes_only_old_tombstones(self, db):
        now = datetime.now(UTC)
        db.add_all(
            [
                health_models.HealthRecordDeletion(
                    user_id=USER, record_id=1, record_type="health_weight", deleted_at=now - timedelta(days=100)
                ),
                health_models.HealthRecordDeletion(
                    user_id=USER, record_id=2, record_type="health_weight", deleted_at=now - timedelta(days=1)
                ),
            ]
        )
        db.flush()

        import modules.health.record_service as health_record_service

        removed = health_record_service.prune_deletions(db)

        assert removed == 1
        assert [d.record_id for d in db.scalars(select(health_models.HealthRecordDeletion))] == [2]

    def test_the_job_runs_daily(self):
        (job,) = health_scheduled_jobs.recurring_jobs()

        assert job.minutes == 24 * 60
        assert job.lock_name == health_scheduled_jobs.PRUNE_LOCK_NAME
