from datetime import date

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
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
        crud.edit_gear_component(component_update(retired.id, retired_date=date(2025, 1, 1)), 1, db)

        assert len(crud.get_gear_components_user_by_gear_id(1, 1, db, active=True)) == 1
        assert [c.id for c in crud.get_gear_components_user_by_gear_id(1, 1, db, active=False)] == [retired.id]

    def test_a_gears_component_list_and_windows_are_bounded(self, db, monkeypatch):
        for _ in range(3):
            crud.create_gear_component(component_create(), 1, db)
        monkeypatch.setattr(core_pagination, "MAX_NUM_RECORDS", 2)

        assert len(crud.get_gear_components_user_by_gear_id(1, 1, db)) == 2
        assert len(crud.list_usage_windows(1, 1, db)) == 2

    def test_usage_windows_carry_the_fitting_dates_of_the_owners_components(self, db):
        created = crud.create_gear_component(component_create(purchase_date=date(2024, 3, 1)), 1, db)
        crud.create_gear_component(component_create(), 2, db)

        windows = crud.list_usage_windows(1, 1, db)

        assert [(w.key, w.start_date, w.end_date) for w in windows] == [(created.id, date(2024, 3, 1), None)]

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
            component_update(created.id, retired_date=date(2025, 1, 1), active=True), 1, db
        )

        assert updated.active is False

    def test_an_unretired_component_keeps_the_submitted_active_flag(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        updated = crud.edit_gear_component(component_update(created.id, active=False), 1, db)

        assert updated.active is False

    def test_edit_never_moves_a_component_to_another_gear(self, db):
        created = crud.create_gear_component(component_create(1), 1, db)

        updated = crud.edit_gear_component(component_update(created.id, 2), 1, db)

        assert updated.gear_id == 1

    def test_edit_and_delete_of_a_foreign_component_are_not_found(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_gear_component(component_update(created.id), 2, db)
        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_gear_component(2, created.id, db)

    def test_delete_removes_the_component(self, db):
        created = crud.create_gear_component(component_create(), 1, db)

        crud.delete_gear_component(1, created.id, db)

        assert crud.get_gear_components_user(1, db) == []
