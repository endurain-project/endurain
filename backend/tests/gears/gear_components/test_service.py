from datetime import date
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.gears.contracts as gears_contracts
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.service as service
from tests._helpers.gears import component_create, component_update, gear_create, install_readers


def _gear(db, gear_type=gear_schema.GearType.BIKE, user_id=1) -> int:
    return gear_crud.create_gear(gear_create("G", gear_type=gear_type), user_id, db).id


class TestCreate:
    def test_a_component_matching_the_gear_type_is_created_and_committed(self, db, commit_spy):
        gear_id = _gear(db)

        created = service.create_gear_component(component_create(gear_id), 1, db)

        assert created.gear_id == gear_id
        commit_spy.assert_called_once_with()

    def test_a_gear_the_user_does_not_own_is_not_found(self, db):
        gear_id = _gear(db, user_id=2)

        with pytest.raises(core_exceptions.NotFoundError):
            service.create_gear_component(component_create(gear_id), 1, db)

    def test_a_type_that_does_not_fit_the_gear_is_refused_and_nothing_is_written(self, db, commit_spy):
        gear_id = _gear(db, gear_schema.GearType.SHOES)

        with pytest.raises(core_exceptions.InvalidInputError, match="shoes"):
            service.create_gear_component(component_create(gear_id, type="chain"), 1, db)

        commit_spy.assert_not_called()
        assert crud.get_gear_components_user(1, db) == []

    def test_a_gear_type_without_a_restriction_accepts_any_type(self, db):
        gear_id = _gear(db, gear_schema.GearType.WETSUIT)

        created = service.create_gear_component(component_create(gear_id, type="anything"), 1, db)

        assert created.type == "anything"


class TestEditAndDelete:
    def test_retiring_before_purchase_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            service.edit_gear_component(
                component_update(1, purchase_date=date(2024, 5, 1), retired_date=date(2024, 5, 1)), 1, db
            )

    def test_edit_commits(self, db, commit_spy):
        gear_id = _gear(db)
        created = crud.create_gear_component(component_create(gear_id), 1, db)

        updated = service.edit_gear_component(component_update(created.id, gear_id, brand="SRAM"), 1, db)

        commit_spy.assert_called_once_with()
        assert updated.brand == "SRAM"

    def test_delete_commits(self, db, commit_spy):
        created = crud.create_gear_component(component_create(), 1, db)

        service.delete_gear_component(1, created.id, db)

        commit_spy.assert_called_once_with()
        assert crud.get_gear_components_user(1, db) == []


class TestListForGear:
    def test_each_component_gets_the_usage_of_its_own_window(self, db):
        first = crud.create_gear_component(component_create(), 1, db)
        second = crud.create_gear_component(component_create(), 1, db)
        reader = MagicMock(
            return_value={
                first.id: gears_contracts.UsageTotals(distance=100.0, time=10.0),
                second.id: gears_contracts.UsageTotals(distance=5.0, time=1.0),
            }
        )
        install_readers(usage_by_window=reader)

        result = service.list_components_for_gear(1, 1, db)

        assert {c.id: (c.current_distance, c.current_time) for c in result} == {
            first.id: (100.0, 10.0),
            second.id: (5.0, 1.0),
        }
        assert sorted(w.key for w in reader.call_args.args[2]) == [first.id, second.id]

    def test_a_component_missing_from_the_totals_reports_zero(self, db):
        crud.create_gear_component(component_create(), 1, db)
        install_readers()

        assert service.list_components_for_gear(1, 1, db)[0].current_distance == 0

    def test_no_components_means_no_usage_query(self, db):
        reader = MagicMock()
        install_readers(usage_by_window=reader)

        assert service.list_components_for_gear(1, 1, db) == []
        reader.assert_not_called()

    def test_the_active_filter_does_not_narrow_the_windows(self, db):
        crud.create_gear_component(component_create(), 1, db)
        inactive = crud.create_gear_component(component_create(), 1, db)
        crud.edit_gear_component(component_update(inactive.id, active=False), 1, db)
        reader = MagicMock(return_value={})
        install_readers(usage_by_window=reader)

        result = service.list_components_for_gear(1, 1, db, active=True)

        assert len(result) == 1
        assert len(reader.call_args.args[2]) == 2


def test_the_user_list_is_bounded(db, monkeypatch):
    for _ in range(3):
        crud.create_gear_component(component_create(), 1, db)
    monkeypatch.setattr(core_pagination, "MAX_NUM_RECORDS", 2)

    assert len(service.list_gear_components(1, db)) == 2


def test_component_types_are_grouped_by_gear_type():
    types = service.read_component_types()

    assert "chain" in types.bike
    assert "cleats" in types.shoes
