import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

import modules.gears.gear.crud as crud
import modules.gears.gear.integration_service as integration
import modules.gears.gear.models as models
import modules.gears.gear.scheduled_jobs as scheduled_jobs
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.service as service
import modules.gears.gear_components.crud as components_crud
import modules.gears.gear_components.integration_service as components_integration
from tests._factories.activities import make_activity
from tests._factories.gears import component_payload, gear_payload
from tests._factories.users import make_user

FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
OLD = datetime(2020, 1, 1, tzinfo=UTC)


def _stamp(db, gear_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(update(models.Gear).where(models.Gear.id == gear_id).values(updated_at=stamp))
    db.flush()


class TestUpdatedAt:
    def test_an_insert_stamps_the_gear(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)

        assert created.updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)
        _stamp(db, created.id, OLD)

        db.execute(update(models.Gear).where(models.Gear.id == created.id).values(nickname="Renamed"))
        db.expire_all()

        assert db.get(models.Gear, created.id).updated_at > OLD

    def test_an_orm_edit_moves_the_stamp(self, db, user):
        created = crud.create_gear(gear_payload(), user.id, db)
        _stamp(db, created.id, OLD)
        db.expire_all()

        edited = crud.edit_gear(created.id, gears_schema.GearUpdate(nickname="New"), user.id, db, if_match="*")

        assert edited.updated_at > OLD


class TestDeletionRecords:
    def test_deleting_a_gear_records_it_and_its_components(self, db, user):
        gear = crud.create_gear(gear_payload(), user.id, db)
        keep = crud.create_gear(gear_payload("Other"), user.id, db)
        component = components_crud.create_gear_component(component_payload(gear.id), user.id, db)
        kept_component = components_crud.create_gear_component(component_payload(keep.id), user.id, db)

        service.delete_gear(gear.id, user.id, db, if_match="*")

        assert [d.record_id for d in integration.list_gear_deletions(user.id, None, FAR_FUTURE, 10, db)] == [gear.id]
        assert [
            d.record_id for d in components_integration.list_gear_component_deletions(user.id, None, FAR_FUTURE, 10, db)
        ] == [component.id]
        assert kept_component.id != component.id

    def test_the_strava_unlink_records_the_gears_and_their_components(self, db, user, other):
        strava = crud.create_gear(gear_payload("Strava", strava_gear_id="b1"), user.id, db)
        plain = crud.create_gear(gear_payload("Plain"), user.id, db)
        component = components_crud.create_gear_component(component_payload(strava.id), user.id, db)
        components_crud.create_gear_component(component_payload(plain.id), user.id, db)
        crud.create_gear(gear_payload("Foreign", strava_gear_id="b2"), other.id, db)

        service.delete_all_strava_gear_for_user(user.id, db)

        assert [d.record_id for d in integration.list_gear_deletions(user.id, None, FAR_FUTURE, 10, db)] == [strava.id]
        assert [
            d.record_id for d in components_integration.list_gear_component_deletions(user.id, None, FAR_FUTURE, 10, db)
        ] == [component.id]
        assert integration.list_gear_deletions(other.id, None, FAR_FUTURE, 10, db) == []

    def test_a_deletion_names_the_sync_type_and_position(self, db, user):
        gear = crud.create_gear(gear_payload(), user.id, db)
        crud.delete_gear(gear.id, user.id, db, if_match="*")

        [deletion] = integration.list_gear_deletions(user.id, None, FAR_FUTURE, 10, db)

        row = db.scalars(select(models.GearDeletion)).one()
        assert (deletion.type, deletion.record_id, deletion.position) == ("gear", gear.id, (row.deleted_at, row.id))


class TestChangedGears:
    def test_pages_in_stamp_then_id_order_with_ties(self, db, user):
        a, b = sorted(
            (crud.create_gear(gear_payload(name), user.id, db) for name in ("A", "B")), key=lambda gear: gear.id
        )
        c = crud.create_gear(gear_payload("C"), user.id, db)
        tie = datetime(2024, 1, 1, tzinfo=UTC)
        _stamp(db, c.id, datetime(2023, 1, 1, tzinfo=UTC))
        _stamp(db, a.id, tie)
        _stamp(db, b.id, tie)

        first = integration.list_changed_gears(user.id, None, FAR_FUTURE, 2, db)
        second = integration.list_changed_gears(user.id, (first[-1].updated_at, first[-1].id), FAR_FUTURE, 2, db)

        assert [g.id for g in first] == [c.id, a.id]
        assert [g.id for g in second] == [b.id]

    def test_until_and_owner_bound_the_page(self, db, user, other):
        mine = crud.create_gear(gear_payload(), user.id, db)
        crud.create_gear(gear_payload(), other.id, db)

        assert [g.id for g in integration.list_changed_gears(user.id, None, FAR_FUTURE, 10, db)] == [mine.id]
        assert integration.list_changed_gears(other.id, None, datetime(2000, 1, 1, tzinfo=UTC), 10, db) == []

    def test_each_gear_carries_its_own_totals(self, db, user):
        gear = crud.create_gear(gear_payload("Ridden", initial_distance=10.0), user.id, db)
        idle = crud.create_gear(gear_payload("Idle"), user.id, db)
        make_activity(db, user.id, gear_id=gear.id, distance=5, total_timer_time=60.0)
        components_crud.create_gear_component(component_payload(gear.id, purchase_value="2.50"), user.id, db)

        changed = integration.list_changed_gears(user.id, None, FAR_FUTURE, 10, db)

        assert {g.id: (g.total_distance, g.total_time, g.total_components_cost) for g in changed} == {
            gear.id: (15.0, 60.0, "2.50"),
            idle.id: (0.0, 0.0, "0.00"),
        }


class TestPrune:
    def test_only_old_tombstones_are_removed(self, db, user):
        old = crud.create_gear(gear_payload("Old"), user.id, db)
        recent = crud.create_gear(gear_payload("Recent"), user.id, db)
        crud.delete_gear(old.id, user.id, db, if_match="*")
        crud.delete_gear(recent.id, user.id, db, if_match="*")
        db.execute(update(models.GearDeletion).where(models.GearDeletion.record_id == old.id).values(deleted_at=OLD))

        removed = service.prune_gear_deletions(datetime.now(UTC), db)

        assert removed == 1
        assert [r.record_id for r in db.scalars(select(models.GearDeletion))] == [recent.id]

    def test_the_registered_prune_job_removes_the_tombstones_and_commits(self, committed_sessions):
        with committed_sessions() as db:
            owner = make_user(db)
            gear = crud.create_gear(gear_payload(), owner.id, db)
            crud.delete_gear(gear.id, owner.id, db, if_match="*")
            db.execute(update(models.GearDeletion).values(deleted_at=OLD))
            db.commit()

        [job] = scheduled_jobs.recurring_jobs()
        job.func()

        with committed_sessions() as db:
            assert db.scalars(select(models.GearDeletion)).all() == []
