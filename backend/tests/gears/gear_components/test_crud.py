import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

import core.exceptions as core_exceptions
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.models as models
import modules.gears.gear_components.schema as schema
from tests._factories.gears import component_payload

FIRST_CREATED = datetime(2024, 1, 1, tzinfo=UTC)


def _create(db, gear_id, user_id, *, index=0, **overrides):
    """Create a component whose creation time is ``index`` seconds after FIRST_CREATED."""
    created = crud.create_gear_component(component_payload(gear_id, **overrides), user_id, db)
    db.execute(
        update(models.GearComponents)
        .where(models.GearComponents.id == created.id)
        .values(created_at=FIRST_CREATED + timedelta(seconds=index))
    )
    db.flush()
    return created


class TestCountOutsideTypes:
    def test_only_this_users_components_of_this_gear_outside_the_types_are_counted(
        self, db, user, other, other_gear, gear
    ):
        crud.create_gear_component(component_payload(gear.id, type="chain"), user.id, db)
        crud.create_gear_component(component_payload(gear.id, type="laces"), user.id, db)
        crud.create_gear_component(component_payload(other_gear.id, type="chain"), user.id, db)
        crud.create_gear_component(component_payload(gear.id, type="chain"), other.id, db)

        assert crud.count_gear_components_outside_types(gear.id, user.id, ["laces", "cleats"], db) == 1
        assert crud.count_gear_components_outside_types(gear.id, user.id, ["chain", "laces"], db) == 0


class TestExpectedUsage:
    def test_the_expected_usage_is_stored_and_read_back(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id, expected_usage=5_000_000), user.id, db)

        assert created.expected_usage == 5_000_000
        assert crud.get_gear_components_user(user.id, db)[0].expected_usage == 5_000_000


class TestReads:
    def test_components_are_scoped_to_their_owner_and_gear(self, db, user, other, other_gear, gear):
        mine = _create(db, gear.id, user.id, index=0)
        elsewhere = _create(db, other_gear.id, user.id, index=1)
        _create(db, gear.id, other.id, index=2)

        assert [c.id for c in crud.get_gear_components_user(user.id, db)] == [mine.id, elsewhere.id]
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(user.id, gear.id, db)] == [mine.id]

    def test_the_user_list_honours_the_limit(self, db, user, gear):
        first = _create(db, gear.id, user.id, index=0)
        _create(db, gear.id, user.id, index=1)

        assert [c.id for c in crud.get_gear_components_user(user.id, db, limit=1)] == [first.id]

    def test_the_active_filter_applies(self, db, user, gear):
        _create(db, gear.id, user.id, index=0)
        retired = _create(db, gear.id, user.id, index=1)
        crud.edit_gear_component(
            retired.id, schema.GearComponentUpdate(retired_date=date(2025, 1, 1)), user.id, db, if_match="*"
        )

        assert len(crud.get_gear_components_user_by_gear_id(user.id, gear.id, db, active=True)) == 1
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(user.id, gear.id, db, active=False)] == [
            retired.id
        ]

    def test_a_gears_components_are_paged_and_counted(self, db, user, other, gear):
        created = [_create(db, gear.id, user.id, index=i) for i in range(3)]
        _create(db, gear.id, other.id, index=3)

        page = crud.get_gear_components_user_by_gear_id(user.id, gear.id, db, page_number=2, num_records=2)

        assert [c.id for c in page] == [created[2].id]
        assert crud.get_gear_components_number_by_gear_id(user.id, gear.id, db) == 3
        assert crud.get_gear_components_number_by_gear_id(user.id, gear.id, db, active=False) == 0

    def test_a_users_components_are_offset_and_counted(self, db, user, other, gear):
        created = [_create(db, gear.id, user.id, index=i) for i in range(3)]
        _create(db, gear.id, other.id, index=3)

        assert [c.id for c in crud.get_gear_components_user(user.id, db, limit=2, offset=1)] == [
            created[1].id,
            created[2].id,
        ]
        assert crud.get_gear_components_number(user.id, db) == 3

    def test_total_cost_sums_the_gears_components_for_its_owner(self, db, user, other, other_gear, gear):
        crud.create_gear_component(component_payload(gear.id, purchase_value="10.50"), user.id, db)
        crud.create_gear_component(component_payload(gear.id, purchase_value="4.50"), user.id, db)
        crud.create_gear_component(component_payload(gear.id, purchase_value="100.00"), other.id, db)
        crud.create_gear_component(component_payload(other_gear.id, purchase_value="100.00"), user.id, db)

        assert crud.get_gear_components_total_cost(gear.id, user.id, db) == 15.0
        assert crud.get_gear_components_total_cost(uuid.uuid4(), user.id, db) == 0.0


class TestOrdering:
    def test_components_created_at_the_same_instant_are_ordered_by_id(self, db, user, gear):
        created = [_create(db, gear.id, user.id, index=0) for _ in range(3)]

        listed = [c.id for c in crud.get_gear_components_user(user.id, db)]

        assert listed == sorted(c.id for c in created)

    def test_the_lists_follow_creation_order_whatever_the_ids(self, db, user, gear):
        created = [_create(db, gear.id, user.id, index=i) for i in (2, 0, 1)]

        expected = [created[1].id, created[2].id, created[0].id]
        assert [c.id for c in crud.get_gear_components_user(user.id, db)] == expected
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(user.id, gear.id, db)] == expected


class TestWrites:
    def test_a_new_component_starts_active_and_staged(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)
        assert created.active is True

        db.rollback()
        assert crud.get_gear_components_user(user.id, db) == []

    def test_a_retired_component_is_always_inactive(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        updated = crud.edit_gear_component(
            created.id,
            schema.GearComponentUpdate(retired_date=date(2025, 1, 1), active=True),
            user.id,
            db,
            if_match="*",
        )

        assert updated.active is False

    def test_an_unretired_component_keeps_the_submitted_active_flag(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        updated = crud.edit_gear_component(
            created.id, schema.GearComponentUpdate(active=False), user.id, db, if_match="*"
        )

        assert updated.active is False

    def test_an_update_cannot_move_a_component_to_another_gear(self):
        with pytest.raises(ValueError):
            schema.GearComponentUpdate(gear_id=uuid.uuid4())

    def test_edit_honours_if_match_and_bumps_the_version(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        updated = crud.edit_gear_component(
            created.id, schema.GearComponentUpdate(brand="SRAM"), user.id, db, if_match=f'"{created.version}"'
        )

        assert updated.version == created.version + 1
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_gear_component(
                created.id, schema.GearComponentUpdate(brand="X"), user.id, db, if_match=f'"{created.version}"'
            )

    def test_edit_and_delete_of_a_foreign_component_are_not_found(self, db, user, other, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear_component(created.id, schema.GearComponentUpdate(brand="x"), other.id, db, if_match="*")
        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear_component(other.id, created.id, db, if_match="*")

    def test_delete_removes_the_component(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        crud.delete_gear_component(user.id, created.id, db, if_match=f'"{created.version}"')

        assert crud.get_gear_components_user(user.id, db) == []

    def test_delete_of_a_stale_version_is_refused_and_keeps_the_component(self, db, user, gear):
        created = crud.create_gear_component(component_payload(gear.id), user.id, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.delete_gear_component(user.id, created.id, db, if_match=f'"{created.version + 1}"')

        assert len(crud.get_gear_components_user(user.id, db)) == 1
