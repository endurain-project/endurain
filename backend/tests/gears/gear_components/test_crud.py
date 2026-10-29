from datetime import date

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear_components.crud as crud
from tests._helpers.gears import component_create, component_update


class TestReads:
    def test_components_are_scoped_to_their_owner_and_gear(self, db):
        mine = crud.create_gear_component(component_create(1), 1, db)
        other_gear = crud.create_gear_component(component_create(2), 1, db)
        crud.create_gear_component(component_create(1), 2, db)

        assert [c.id for c in crud.get_gear_components_user(1, db)] == [mine.id, other_gear.id]
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, 1, db)] == [mine.id]

    def test_the_user_list_honours_the_limit(self, db):
        first = crud.create_gear_component(component_create(), 1, db)
        crud.create_gear_component(component_create(), 1, db)

        assert [c.id for c in crud.get_gear_components_user(1, db, limit=1)] == [first.id]

    def test_the_active_filter_applies(self, db):
        crud.create_gear_component(component_create(), 1, db)
        retired = crud.create_gear_component(component_create(), 1, db)
        crud.edit_gear_component(retired.id, component_update(retired_date=date(2025, 1, 1)), 1, db, if_match="*")

        assert len(crud.get_gear_components_user_by_gear_id(1, 1, db, active=True)) == 1
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, 1, db, active=False)] == [retired.id]

    def test_a_gears_components_are_paged_and_counted(self, db):
        created = [crud.create_gear_component(component_create(), 1, db) for _ in range(3)]
        crud.create_gear_component(component_create(), 2, db)

        page = crud.get_gear_components_user_by_gear_id(1, 1, db, page_number=2, num_records=2)

        assert [c.id for c in page] == [created[2].id]
        assert crud.get_gear_components_number_by_gear_id(1, 1, db) == 3
        assert crud.get_gear_components_number_by_gear_id(1, 1, db, active=False) == 0

    def test_a_users_components_are_offset_and_counted(self, db):
        created = [crud.create_gear_component(component_create(), 1, db) for _ in range(3)]
        crud.create_gear_component(component_create(), 2, db)

        assert [c.id for c in crud.get_gear_components_user(1, db, limit=2, offset=1)] == [created[1].id, created[2].id]
        assert crud.get_gear_components_number(1, db) == 3

    def test_total_cost_sums_the_gears_components_for_its_owner(self, db):
        crud.create_gear_component(component_create(purchase_value=10.5), 1, db)
        crud.create_gear_component(component_create(purchase_value=4.5), 1, db)
        crud.create_gear_component(component_create(purchase_value=100.0), 2, db)
        crud.create_gear_component(component_create(2, purchase_value=100.0), 1, db)

        assert crud.get_gear_components_total_cost(1, 1, db) == 15.0
        assert crud.get_gear_components_total_cost(9, 1, db) == 0.0


class TestWrites:
    def test_a_new_component_starts_active_and_staged(self, db):
        created = crud.create_gear_component(component_create(), 1, db)
        assert created.active is True

        db.rollback()
        assert crud.get_gear_components_user(1, db) == []

    def test_a_retired_component_is_always_inactive(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        updated = crud.edit_gear_component(
            created.id, component_update(retired_date=date(2025, 1, 1), active=True), 1, db, if_match="*"
        )

        assert updated.active is False

    def test_an_unretired_component_keeps_the_submitted_active_flag(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        updated = crud.edit_gear_component(created.id, component_update(active=False), 1, db, if_match="*")

        assert updated.active is False

    def test_an_update_cannot_move_a_component_to_another_gear(self):
        with pytest.raises(ValueError):
            component_update(gear_id=2)

    def test_edit_honours_if_match_and_bumps_the_version(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        updated = crud.edit_gear_component(
            created.id, component_update(brand="SRAM"), 1, db, if_match=f'"{created.version}"'
        )

        assert updated.version == created.version + 1
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_gear_component(created.id, component_update(brand="X"), 1, db, if_match=f'"{created.version}"')

    def test_edit_and_delete_of_a_foreign_component_are_not_found(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear_component(created.id, component_update(brand="x"), 2, db, if_match="*")
        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear_component(2, created.id, db, if_match="*")

    def test_delete_removes_the_component(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        crud.delete_gear_component(1, created.id, db, if_match=f'"{created.version}"')

        assert crud.get_gear_components_user(1, db) == []

    def test_delete_of_a_stale_version_is_refused_and_keeps_the_component(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.delete_gear_component(1, created.id, db, if_match=f'"{created.version + 1}"')

        assert len(crud.get_gear_components_user(1, db)) == 1
