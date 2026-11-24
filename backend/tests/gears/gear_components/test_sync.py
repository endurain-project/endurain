import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.integration_service as integration
import modules.gears.gear_components.models as models
import modules.gears.gear_components.scheduled_jobs as scheduled_jobs
import modules.gears.gear_components.schema as schema
import modules.gears.gear_components.service as service
from tests._factories.gears import component_payload, make_gear
from tests._factories.users import make_user

FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
OLD = datetime(2020, 1, 1, tzinfo=UTC)


def _stamp(db, component_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(update(models.GearComponents).where(models.GearComponents.id == component_id).values(updated_at=stamp))
    db.flush()


class TestUpdatedAt:
    def test_an_insert_stamps_the_component(self, db, user, gear):
        assert crud.create_gear_component(component_payload(gear.id), user.id, db).updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)
        _stamp(db, created.id, OLD)

        db.execute(update(models.GearComponents).where(models.GearComponents.id == created.id).values(brand="SRAM"))
        db.expire_all()

        assert db.get(models.GearComponents, created.id).updated_at > OLD

    def test_an_orm_edit_moves_the_stamp(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)
        _stamp(db, created.id, OLD)
        db.expire_all()

        edited = crud.edit_gear_component(
            created.id, schema.GearComponentUpdate(brand="SRAM"), user.id, db, if_match="*"
        )

        assert edited.updated_at > OLD


class TestDeletionRecords:
    def test_deleting_a_component_records_it(self, db, user, gear):
        component = crud.create_gear_component(component_payload(gear.id), user.id, db)
        kept = crud.create_gear_component(component_payload(gear.id), user.id, db)

        crud.delete_gear_component(user.id, component.id, db, if_match="*")

        [deletion] = integration.list_gear_component_deletions(user.id, None, FAR_FUTURE, 10, db)
        row = db.scalars(select(models.GearComponentDeletion)).one()
        assert (deletion.type, deletion.record_id, deletion.position) == (
            "gear_component",
            component.id,
            (row.deleted_at, row.id),
        )
        assert kept.id != deletion.record_id

    def test_recording_a_gears_deletion_covers_only_its_components_of_that_user(
        self, db, user, other, other_gear, gear
    ):
        mine = crud.create_gear_component(component_payload(gear.id), user.id, db)
        crud.create_gear_component(component_payload(other_gear.id), user.id, db)
        crud.create_gear_component(component_payload(gear.id), other.id, db)

        integration.record_gear_component_deletions([gear.id], user.id, db)

        assert [d.record_id for d in integration.list_gear_component_deletions(user.id, None, FAR_FUTURE, 10, db)] == [
            mine.id
        ]
        assert integration.list_gear_component_deletions(other.id, None, FAR_FUTURE, 10, db) == []


class TestChangedComponents:
    def test_pages_in_stamp_then_id_order_with_ties(self, db, user, gear):
        a, b, c = (crud.create_gear_component(component_payload(gear.id), user.id, db) for _ in range(3))
        tie = datetime(2024, 1, 1, tzinfo=UTC)
        _stamp(db, c.id, datetime(2023, 1, 1, tzinfo=UTC))
        _stamp(db, a.id, tie)
        _stamp(db, b.id, tie)

        first = integration.list_changed_gear_components(user.id, None, FAR_FUTURE, 2, db)
        second = integration.list_changed_gear_components(
            user.id, (first[-1].updated_at, first[-1].id), FAR_FUTURE, 2, db
        )

        tied_low, tied_high = sorted((a.id, b.id))
        assert [x.id for x in first] == [c.id, tied_low]
        assert [x.id for x in second] == [tied_high]

    def test_until_and_owner_bound_the_page(self, db, user, other, gear):
        mine = crud.create_gear_component(component_payload(gear.id), user.id, db)
        crud.create_gear_component(component_payload(gear.id), other.id, db)

        assert [x.id for x in integration.list_changed_gear_components(user.id, None, FAR_FUTURE, 10, db)] == [mine.id]
        assert integration.list_changed_gear_components(other.id, None, datetime(2000, 1, 1, tzinfo=UTC), 10, db) == []


class TestPrune:
    def test_only_old_tombstones_are_removed(self, db, user, gear):
        old = crud.create_gear_component(component_payload(gear.id), user.id, db)
        recent = crud.create_gear_component(component_payload(gear.id), user.id, db)
        crud.delete_gear_component(user.id, old.id, db, if_match="*")
        crud.delete_gear_component(user.id, recent.id, db, if_match="*")
        db.execute(
            update(models.GearComponentDeletion)
            .where(models.GearComponentDeletion.record_id == old.id)
            .values(deleted_at=OLD)
        )

        removed = service.prune_gear_component_deletions(datetime.now(UTC), db)

        assert removed == 1
        assert [r.record_id for r in db.scalars(select(models.GearComponentDeletion))] == [recent.id]

    def test_the_registered_prune_job_removes_the_tombstones_and_commits(self, committed_sessions):
        with committed_sessions() as db:
            owner = make_user(db)
            gear = make_gear(db, owner.id)
            component = crud.create_gear_component(component_payload(gear.id), owner.id, db)
            crud.delete_gear_component(owner.id, component.id, db, if_match="*")
            db.execute(update(models.GearComponentDeletion).values(deleted_at=OLD))
            db.commit()

        [job] = scheduled_jobs.recurring_jobs()
        job.func()

        with committed_sessions() as db:
            assert db.scalars(select(models.GearComponentDeletion)).all() == []
