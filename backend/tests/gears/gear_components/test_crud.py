import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

import core.exceptions as core_exceptions
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.models as models
from tests._helpers.gears import component_create, component_update

GEAR = uuid.uuid4()
OTHER_GEAR = uuid.uuid4()
FIRST_CREATED = datetime(2024, 1, 1, tzinfo=UTC)


def _create(db, gear_id=GEAR, user_id=1, *, index=0, **overrides):
    """Create a component whose creation time is ``index`` seconds after FIRST_CREATED."""
    created = crud.create_gear_component(component_create(gear_id, **overrides), user_id, db)
    db.execute(
        update(models.GearComponents)
        .where(models.GearComponents.id == created.id)
        .values(created_at=FIRST_CREATED + timedelta(seconds=index))
    )
    db.flush()
    return created


class TestCountOutsideTypes:
    def test_only_this_users_components_of_this_gear_outside_the_types_are_counted(self, db):
        crud.create_gear_component(component_create(GEAR, type="chain"), 1, db)
        crud.create_gear_component(component_create(GEAR, type="laces"), 1, db)
        crud.create_gear_component(component_create(OTHER_GEAR, type="chain"), 1, db)
        crud.create_gear_component(component_create(GEAR, type="chain"), 2, db)

        assert crud.count_gear_components_outside_types(GEAR, 1, ["laces", "cleats"], db) == 1
        assert crud.count_gear_components_outside_types(GEAR, 1, ["chain", "laces"], db) == 0


class TestExpectedUsage:
    def test_the_expected_usage_is_stored_and_read_back(self, db):
        created = crud.create_gear_component(component_create(GEAR, expected_usage=5_000_000), 1, db)

        assert created.expected_usage == 5_000_000
        assert crud.get_gear_components_user(1, db)[0].expected_usage == 5_000_000


class TestReads:
    def test_components_are_scoped_to_their_owner_and_gear(self, db):
        mine = _create(db, GEAR, 1, index=0)
        other_gear = _create(db, OTHER_GEAR, 1, index=1)
        _create(db, GEAR, 2, index=2)

        assert [c.id for c in crud.get_gear_components_user(1, db)] == [mine.id, other_gear.id]
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, GEAR, db)] == [mine.id]

    def test_the_user_list_honours_the_limit(self, db):
        first = _create(db, index=0)
        _create(db, index=1)

        assert [c.id for c in crud.get_gear_components_user(1, db, limit=1)] == [first.id]

    def test_the_active_filter_applies(self, db):
        _create(db, index=0)
        retired = _create(db, index=1)
        crud.edit_gear_component(retired.id, component_update(retired_date=date(2025, 1, 1)), 1, db, if_match="*")

        assert len(crud.get_gear_components_user_by_gear_id(1, GEAR, db, active=True)) == 1
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, GEAR, db, active=False)] == [retired.id]

    def test_a_gears_components_are_paged_and_counted(self, db):
        created = [_create(db, index=i) for i in range(3)]
        _create(db, GEAR, 2, index=3)

        page = crud.get_gear_components_user_by_gear_id(1, GEAR, db, page_number=2, num_records=2)

        assert [c.id for c in page] == [created[2].id]
        assert crud.get_gear_components_number_by_gear_id(1, GEAR, db) == 3
        assert crud.get_gear_components_number_by_gear_id(1, GEAR, db, active=False) == 0

    def test_a_users_components_are_offset_and_counted(self, db):
        created = [_create(db, index=i) for i in range(3)]
        _create(db, GEAR, 2, index=3)

        assert [c.id for c in crud.get_gear_components_user(1, db, limit=2, offset=1)] == [created[1].id, created[2].id]
        assert crud.get_gear_components_number(1, db) == 3

    def test_total_cost_sums_the_gears_components_for_its_owner(self, db):
        crud.create_gear_component(component_create(GEAR, purchase_value="10.50"), 1, db)
        crud.create_gear_component(component_create(GEAR, purchase_value="4.50"), 1, db)
        crud.create_gear_component(component_create(GEAR, purchase_value="100.00"), 2, db)
        crud.create_gear_component(component_create(OTHER_GEAR, purchase_value="100.00"), 1, db)

        assert crud.get_gear_components_total_cost(GEAR, 1, db) == 15.0
        assert crud.get_gear_components_total_cost(uuid.uuid4(), 1, db) == 0.0


class TestOrdering:
    def test_the_user_list_orders_by_creation_time_then_id(self, mock_db):
        crud.get_gear_components_user(1, mock_db)

        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY gear_components.created_at, gear_components.id" in compiled

    def test_the_gear_list_orders_by_creation_time_then_id(self, mock_db):
        crud.get_gear_components_user_by_gear_id(1, GEAR, mock_db)

        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY gear_components.created_at, gear_components.id" in compiled

    def test_the_lists_follow_creation_order_whatever_the_ids(self, db):
        created = [_create(db, index=i) for i in (2, 0, 1)]

        expected = [created[1].id, created[2].id, created[0].id]
        assert [c.id for c in crud.get_gear_components_user(1, db)] == expected
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, GEAR, db)] == expected


class TestWrites:
    def test_a_new_component_starts_active_and_staged(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)
        assert created.active is True

        db.rollback()
        assert crud.get_gear_components_user(1, db) == []

    def test_a_retired_component_is_always_inactive(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        updated = crud.edit_gear_component(
            created.id, component_update(retired_date=date(2025, 1, 1), active=True), 1, db, if_match="*"
        )

        assert updated.active is False

    def test_an_unretired_component_keeps_the_submitted_active_flag(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        updated = crud.edit_gear_component(created.id, component_update(active=False), 1, db, if_match="*")

        assert updated.active is False

    def test_an_update_cannot_move_a_component_to_another_gear(self):
        with pytest.raises(ValueError):
            component_update(gear_id=OTHER_GEAR)

    def test_edit_honours_if_match_and_bumps_the_version(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        updated = crud.edit_gear_component(
            created.id, component_update(brand="SRAM"), 1, db, if_match=f'"{created.version}"'
        )

        assert updated.version == created.version + 1
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_gear_component(created.id, component_update(brand="X"), 1, db, if_match=f'"{created.version}"')

    def test_edit_and_delete_of_a_foreign_component_are_not_found(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear_component(created.id, component_update(brand="x"), 2, db, if_match="*")
        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear_component(2, created.id, db, if_match="*")

    def test_delete_removes_the_component(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        crud.delete_gear_component(1, created.id, db, if_match=f'"{created.version}"')

        assert crud.get_gear_components_user(1, db) == []

    def test_delete_of_a_stale_version_is_refused_and_keeps_the_component(self, db):
        created = crud.create_gear_component(component_create(GEAR), 1, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.delete_gear_component(1, created.id, db, if_match=f'"{created.version + 1}"')

        assert len(crud.get_gear_components_user(1, db)) == 1
