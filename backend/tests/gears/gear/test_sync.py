import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

import modules.gears.contracts as gears_contracts
import modules.gears.gear.crud as crud
import modules.gears.gear.integration_service as integration
import modules.gears.gear.models as models
import modules.gears.gear.scheduled_jobs as scheduled_jobs
import modules.gears.gear.service as service
import modules.gears.gear_components.crud as components_crud
import modules.gears.gear_components.integration_service as components_integration
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.gears import component_create, gear_create, install_readers

FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)
OLD = datetime(2020, 1, 1)


def _install_component_recorder() -> None:
    install_readers(record_component_deletions=components_integration.record_gear_component_deletions)


def _stamp(db, gear_id: uuid.UUID, stamp: datetime) -> None:
    db.execute(update(models.Gear).where(models.Gear.id == gear_id).values(updated_at=stamp))
    db.flush()


class TestUpdatedAt:
    def test_an_insert_stamps_the_gear(self, db):
        created = crud.create_gear(gear_create(), MOCK_USER_ID, db)

        assert created.updated_at is not None

    def test_a_core_update_that_leaves_the_stamp_out_moves_it(self, db):
        created = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        _stamp(db, created.id, OLD)

        db.execute(update(models.Gear).where(models.Gear.id == created.id).values(nickname="Renamed"))
        db.expire_all()

        assert db.get(models.Gear, created.id).updated_at > OLD

    def test_an_orm_edit_moves_the_stamp(self, db):
        created = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        _stamp(db, created.id, OLD)
        db.expire_all()

        edited = crud.edit_gear(
            created.id, service.gears_schema.GearUpdate(nickname="New"), MOCK_USER_ID, db, if_match="*"
        )

        assert edited.updated_at > OLD


class TestDeletionRecords:
    def test_deleting_a_gear_records_it_and_its_components(self, db):
        _install_component_recorder()
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        keep = crud.create_gear(gear_create("Other"), MOCK_USER_ID, db)
        component = components_crud.create_gear_component(component_create(gear.id), MOCK_USER_ID, db)
        kept_component = components_crud.create_gear_component(component_create(keep.id), MOCK_USER_ID, db)

        service.delete_gear(gear.id, MOCK_USER_ID, db, if_match="*")

        assert [d.record_id for d in integration.list_gear_deletions(MOCK_USER_ID, None, FAR_FUTURE, 10, db)] == [
            gear.id
        ]
        assert [
            d.record_id
            for d in components_integration.list_gear_component_deletions(MOCK_USER_ID, None, FAR_FUTURE, 10, db)
        ] == [component.id]
        assert kept_component.id != component.id

    def test_the_strava_unlink_records_the_gears_and_their_components(self, db):
        _install_component_recorder()
        strava = crud.create_gear(gear_create("Strava", strava_gear_id="b1"), MOCK_USER_ID, db)
        plain = crud.create_gear(gear_create("Plain"), MOCK_USER_ID, db)
        component = components_crud.create_gear_component(component_create(strava.id), MOCK_USER_ID, db)
        components_crud.create_gear_component(component_create(plain.id), MOCK_USER_ID, db)
        crud.create_gear(gear_create("Foreign", strava_gear_id="b2"), OTHER_USER_ID, db)

        service.delete_all_strava_gear_for_user(MOCK_USER_ID, db)

        assert [d.record_id for d in integration.list_gear_deletions(MOCK_USER_ID, None, FAR_FUTURE, 10, db)] == [
            strava.id
        ]
        assert [
            d.record_id
            for d in components_integration.list_gear_component_deletions(MOCK_USER_ID, None, FAR_FUTURE, 10, db)
        ] == [component.id]
        assert integration.list_gear_deletions(OTHER_USER_ID, None, FAR_FUTURE, 10, db) == []

    def test_a_deletion_names_the_sync_type_and_position(self, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        crud.delete_gear(gear.id, MOCK_USER_ID, db, if_match="*")

        [deletion] = integration.list_gear_deletions(MOCK_USER_ID, None, FAR_FUTURE, 10, db)

        row = db.scalars(select(models.GearDeletion)).one()
        assert (deletion.type, deletion.record_id, deletion.position) == ("gear", gear.id, (row.deleted_at, row.id))


class TestChangedGears:
    def test_pages_in_stamp_then_id_order_with_ties(self, db):
        a, b = sorted(
            (crud.create_gear(gear_create(name), MOCK_USER_ID, db) for name in ("A", "B")), key=lambda gear: gear.id
        )
        c = crud.create_gear(gear_create("C"), MOCK_USER_ID, db)
        tie = datetime(2024, 1, 1)
        _stamp(db, c.id, datetime(2023, 1, 1))
        _stamp(db, a.id, tie)
        _stamp(db, b.id, tie)
        install_readers()

        first = integration.list_changed_gears(MOCK_USER_ID, None, FAR_FUTURE, 2, db)
        second = integration.list_changed_gears(MOCK_USER_ID, (first[-1].updated_at, first[-1].id), FAR_FUTURE, 2, db)

        assert [g.id for g in first] == [c.id, a.id]
        assert [g.id for g in second] == [b.id]

    def test_until_and_owner_bound_the_page(self, db):
        mine = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        crud.create_gear(gear_create(), OTHER_USER_ID, db)
        install_readers()

        assert [g.id for g in integration.list_changed_gears(MOCK_USER_ID, None, FAR_FUTURE, 10, db)] == [mine.id]
        assert integration.list_changed_gears(OTHER_USER_ID, None, datetime(2000, 1, 1, tzinfo=UTC), 10, db) == []

    def test_each_gear_carries_its_totals(self, db):
        crud.create_gear(gear_create(initial_distance=10.0), MOCK_USER_ID, db)
        install_readers(
            usage=lambda gear_id, user_id, _db: gears_contracts.UsageTotals(distance=5.0, time=60.0),
            components_cost=lambda gear_id, user_id, _db: 2.5,
        )

        [gear] = integration.list_changed_gears(MOCK_USER_ID, None, FAR_FUTURE, 10, db)

        assert (gear.total_distance, gear.total_time, gear.total_components_cost) == (15.0, 60.0, "2.50")


class TestPrune:
    def test_only_old_tombstones_are_removed(self, db):
        old = crud.create_gear(gear_create("Old"), MOCK_USER_ID, db)
        recent = crud.create_gear(gear_create("Recent"), MOCK_USER_ID, db)
        crud.delete_gear(old.id, MOCK_USER_ID, db, if_match="*")
        crud.delete_gear(recent.id, MOCK_USER_ID, db, if_match="*")
        db.execute(update(models.GearDeletion).where(models.GearDeletion.record_id == old.id).values(deleted_at=OLD))

        removed = service.prune_gear_deletions(datetime.now(UTC).replace(tzinfo=None), db)

        assert removed == 1
        assert [r.record_id for r in db.scalars(select(models.GearDeletion))] == [recent.id]

    def test_the_job_is_scheduled_daily(self):
        [job] = scheduled_jobs.recurring_jobs()

        assert job.lock_name == scheduled_jobs.PRUNE_LOCK_NAME
