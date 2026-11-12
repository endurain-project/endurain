import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.integration_service as integration
import modules.gears.gear_components.models as models
import modules.gears.gear_components.scheduled_jobs as scheduled_jobs
import modules.gears.gear_components.service as service
from tests._helpers.gears import component_create, component_update

FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
OLD = datetime(2020, 1, 1)
GEAR = uuid.uuid4()
OTHER_GEAR = uuid.uuid4()


def _stamp(db, component_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(update(models.GearComponents).where(models.GearComponents.id == component_id).values(updated_at=stamp))
    db.flush()


class TestUpdatedAt:
    def test_an_insert_stamps_the_component(self, db):
        assert crud.create_gear_component(component_create(GEAR), 1, db).updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)
        _stamp(db, created.id, OLD)

        db.execute(update(models.GearComponents).where(models.GearComponents.id == created.id).values(brand="SRAM"))
        db.expire_all()

        assert db.get(models.GearComponents, created.id).updated_at > OLD

    def test_an_orm_edit_moves_the_stamp(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)
        _stamp(db, created.id, OLD)
        db.expire_all()

        edited = crud.edit_gear_component(created.id, component_update(brand="SRAM"), 1, db, if_match="*")

        assert edited.updated_at > OLD


class TestDeletionRecords:
    def test_deleting_a_component_records_it(self, db):
        component = crud.create_gear_component(component_create(GEAR), 1, db)
        kept = crud.create_gear_component(component_create(GEAR), 1, db)

        crud.delete_gear_component(1, component.id, db, if_match="*")

        [deletion] = integration.list_gear_component_deletions(1, None, FAR_FUTURE, 10, db)
        row = db.scalars(select(models.GearComponentDeletion)).one()
        assert (deletion.type, deletion.record_id, deletion.position) == (
            "gear_component",
            component.id,
            (row.deleted_at, row.id),
        )
        assert kept.id != deletion.record_id

    def test_recording_a_gears_deletion_covers_only_its_components_of_that_user(self, db):
        mine = crud.create_gear_component(component_create(GEAR), 1, db)
        crud.create_gear_component(component_create(OTHER_GEAR), 1, db)
        crud.create_gear_component(component_create(GEAR), 2, db)

        integration.record_gear_component_deletions([GEAR], 1, db)

        assert [d.record_id for d in integration.list_gear_component_deletions(1, None, FAR_FUTURE, 10, db)] == [
            mine.id
        ]
        assert integration.list_gear_component_deletions(2, None, FAR_FUTURE, 10, db) == []


class TestChangedComponents:
    def test_pages_in_stamp_then_id_order_with_ties(self, db):
        a, b, c = (crud.create_gear_component(component_create(GEAR), 1, db) for _ in range(3))
        tie = datetime(2024, 1, 1)
        _stamp(db, c.id, datetime(2023, 1, 1))
        _stamp(db, a.id, tie)
        _stamp(db, b.id, tie)

        first = integration.list_changed_gear_components(1, None, FAR_FUTURE, 2, db)
        second = integration.list_changed_gear_components(1, (first[-1].updated_at, first[-1].id), FAR_FUTURE, 2, db)

        tied_low, tied_high = sorted((a.id, b.id))
        assert [x.id for x in first] == [c.id, tied_low]
        assert [x.id for x in second] == [tied_high]

    def test_until_and_owner_bound_the_page(self, db):
        mine = crud.create_gear_component(component_create(GEAR), 1, db)
        crud.create_gear_component(component_create(GEAR), 2, db)

        assert [x.id for x in integration.list_changed_gear_components(1, None, FAR_FUTURE, 10, db)] == [mine.id]
        assert integration.list_changed_gear_components(1, None, datetime(2000, 1, 1, tzinfo=UTC), 10, db) == []


class TestPrune:
    def test_only_old_tombstones_are_removed(self, db):
        old = crud.create_gear_component(component_create(GEAR), 1, db)
        recent = crud.create_gear_component(component_create(GEAR), 1, db)
        crud.delete_gear_component(1, old.id, db, if_match="*")
        crud.delete_gear_component(1, recent.id, db, if_match="*")
        db.execute(
            update(models.GearComponentDeletion)
            .where(models.GearComponentDeletion.record_id == old.id)
            .values(deleted_at=OLD)
        )

        removed = service.prune_gear_component_deletions(datetime.now(UTC).replace(tzinfo=None), db)

        assert removed == 1
        assert [r.record_id for r in db.scalars(select(models.GearComponentDeletion))] == [recent.id]

    def test_the_job_is_scheduled_daily(self):
        [job] = scheduled_jobs.recurring_jobs()

        assert job.lock_name == scheduled_jobs.PRUNE_LOCK_NAME
