from datetime import date
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.schema as schema
import modules.gears.gear_components.service as service


def _component(gear_id=1, **overrides) -> schema.GearComponentCreate:
    return schema.GearComponentCreate(
        **{"gear_id": gear_id, "type": "chain", "brand": "Shimano", "model": "XT", **overrides}
    )


def _update(component_id: int, gear_id: int = 1, **overrides) -> schema.GearComponentUpdate:
    fields = {"gear_id": gear_id, "type": "chain", "brand": "Shimano", "model": "XT", **overrides}
    return schema.GearComponentUpdate(id=component_id, **fields)


def _gear(db, gear_type=gear_schema.GearType.BIKE, user_id=1) -> int:
    return gear_crud.create_gear(gear_schema.GearCreate(nickname="G", gear_type=gear_type), user_id, db).id


class TestCreate:
    def test_a_component_matching_the_gear_type_is_created_and_committed(self, db):
        gear_id = _gear(db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        created = service.create_gear_component(_component(gear_id), 1, db)

        assert created.gear_id == gear_id
        spy.assert_called_once_with()

    def test_a_gear_the_user_does_not_own_is_not_found(self, db):
        gear_id = _gear(db, user_id=2)

        with pytest.raises(core_exceptions.NotFoundError):
            service.create_gear_component(_component(gear_id), 1, db)

    def test_a_type_that_does_not_fit_the_gear_is_refused_and_nothing_is_written(self, db):
        gear_id = _gear(db, gear_schema.GearType.SHOES)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        with pytest.raises(core_exceptions.InvalidInputError, match="shoes"):
            service.create_gear_component(_component(gear_id, type="chain"), 1, db)

        spy.assert_not_called()
        assert crud.get_gear_components_user(1, db) == []

    def test_a_gear_type_without_a_restriction_accepts_any_type(self, db):
        gear_id = _gear(db, gear_schema.GearType.WETSUIT)

        created = service.create_gear_component(_component(gear_id, type="anything"), 1, db)

        assert created.type == "anything"


class TestEdit:
    def test_retiring_before_purchase_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            service.edit_gear_component(
                _update(1, purchase_date=date(2024, 5, 1), retired_date=date(2024, 5, 1)),
                1,
                db,
            )

    def test_edit_commits(self, db):
        gear_id = _gear(db)
        created = service.create_gear_component(_component(gear_id), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        updated = service.edit_gear_component(_update(created.id, gear_id, brand="SRAM"), 1, db)

        spy.assert_called_once_with()
        assert updated.brand == "SRAM"

    def test_delete_commits(self, db):
        gear_id = _gear(db)
        created = service.create_gear_component(_component(gear_id), 1, db)
        spy = MagicMock(wraps=db.commit)
        db.commit = spy

        service.delete_gear_component(1, created.id, db)

        spy.assert_called_once_with()
        assert crud.get_gear_components_user(1, db) == []


class TestListForGear:
    def test_each_component_gets_the_usage_of_its_own_window(self, db):
        gear_id = _gear(db)
        first = service.create_gear_component(_component(gear_id), 1, db)
        second = service.create_gear_component(_component(gear_id), 1, db)
        reader = MagicMock(
            return_value={
                first.id: gears_contracts.UsageTotals(distance=100.0, time=10.0),
                second.id: gears_contracts.UsageTotals(distance=5.0, time=1.0),
            }
        )
        gears_contributor_registry.register_gear_usage_by_window_reader(reader)

        result = service.list_components_for_gear(gear_id, 1, db)

        assert {c.id: (c.current_distance, c.current_time) for c in result} == {
            first.id: (100.0, 10.0),
            second.id: (5.0, 1.0),
        }
        assert sorted(w.key for w in reader.call_args.args[2]) == [first.id, second.id]

    def test_a_component_missing_from_the_totals_reports_zero(self, db):
        gear_id = _gear(db)
        service.create_gear_component(_component(gear_id), 1, db)
        gears_contributor_registry.register_gear_usage_by_window_reader(lambda *_: {})

        assert service.list_components_for_gear(gear_id, 1, db)[0].current_distance == 0

    def test_no_components_means_no_usage_query(self, db):
        reader = MagicMock()
        gears_contributor_registry.register_gear_usage_by_window_reader(reader)

        assert service.list_components_for_gear(1, 1, db) == []
        reader.assert_not_called()

    def test_the_active_filter_does_not_narrow_the_windows(self, db):
        gear_id = _gear(db)
        service.create_gear_component(_component(gear_id), 1, db)
        retired = service.create_gear_component(_component(gear_id), 1, db)
        service.edit_gear_component(_update(retired.id, gear_id, active=False), 1, db)
        reader = MagicMock(return_value={})
        gears_contributor_registry.register_gear_usage_by_window_reader(reader)

        result = service.list_components_for_gear(gear_id, 1, db, active=True)

        assert len(result) == 1
        assert len(reader.call_args.args[2]) == 2


def test_component_types_are_grouped_by_gear_type():
    types = service.read_component_types()

    assert "chain" in types.bike
    assert "cleats" in types.shoes
