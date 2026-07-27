from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


def _make_gc_update(**kwargs):
    from pydantic import BaseModel

    class GCUpdate(BaseModel):
        id: int = 1
        brand: str | None = None
        model: str | None = None
        retired_date: object = None
        active: object = None

    return GCUpdate(**kwargs)


class TestGetGearComponentsUser:
    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_success(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        c = mock_model(m.GearComponents, id=1, user_id=1)
        setup_mock_execute(mock_db, return_scalars_all=[c])
        r = crud.get_gear_components_user(user_id=1, db=mock_db)
        assert r == [c]

    def test_empty(self, mock_db):
        import modules.gears.gear_components.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_gear_components_user(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_gear_components_user(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetGearComponentsUserByGearId:
    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_success(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        c = mock_model(m.GearComponents, id=1, gear_id=1, user_id=1)
        setup_mock_execute(mock_db, return_scalars_all=[c])
        r = crud.get_gear_components_user_by_gear_id(user_id=1, gear_id=1, db=mock_db)
        assert r == [c]

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_success_active_filter(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        c = mock_model(m.GearComponents, id=1, gear_id=1, user_id=1, active=True)
        setup_mock_execute(mock_db, return_scalars_all=[c])
        r = crud.get_gear_components_user_by_gear_id(user_id=1, gear_id=1, db=mock_db, active=True)
        assert r == [c]

    def test_empty(self, mock_db):
        import modules.gears.gear_components.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_gear_components_user_by_gear_id(user_id=1, gear_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_gear_components_user_by_gear_id(user_id=1, gear_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCreateGearComponent:
    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    @patch("modules.gears.gear_components.crud.gear_components_models.GearComponents")
    def test_success(self, mock_gc_cls, mock_db):
        from datetime import datetime

        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.schema as s

        gc = s.GearComponentCreate(
            gear_id=1,
            type="chain",
            brand="Shimano",
            model="Ultegra",
            purchase_date=datetime(2024, 1, 1),
            expected_kms=5000,
            purchase_value=150.0,
        )
        r = crud.create_gear_component(gear_component=gc, user_id=1, db=mock_db)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert r is not None

    @patch("modules.gears.gear_components.crud.gear_components_models.GearComponents")
    def test_db_error(self, mock_gc_cls, mock_db):
        from datetime import datetime

        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.schema as s

        mock_db.add.side_effect = SQLAlchemyError("err")

        gc = s.GearComponentCreate(
            gear_id=1,
            type="chain",
            brand="Shimano",
            model="Ultegra",
            purchase_date=datetime(2024, 1, 1),
            expected_kms=5000,
            purchase_value=150.0,
        )
        with pytest.raises(HTTPException) as e:
            crud.create_gear_component(gear_component=gc, user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestEditGearComponent:
    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_success(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        from pydantic import BaseModel

        class GCUpdate(BaseModel):
            id: int = 1
            brand: str = "SRAM"
            model: str = "Red"

        r = crud.edit_gear_component(gear_component=GCUpdate(), user_id=1, db=mock_db)
        assert r is db_gc
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(db_gc)

    def test_not_found(self, mock_db):
        import modules.gears.gear_components.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)

        from pydantic import BaseModel

        class GCUpdate(BaseModel):
            id: int = 999
            brand: str = "SRAM"

        with pytest.raises(HTTPException) as e:
            crud.edit_gear_component(gear_component=GCUpdate(), user_id=1, db=mock_db)
        assert e.value.status_code == 404

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_retired_date_sets_active_false(self, mock_db):
        from datetime import datetime

        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        crud.edit_gear_component(
            gear_component=_make_gc_update(id=1, retired_date=datetime(2024, 6, 1)),
            user_id=1,
            db=mock_db,
        )
        assert db_gc.active is False

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_retired_date_overrides_explicit_active(self, mock_db):
        # A retired component is always inactive, even when the client
        # explicitly sends active=true in the same request.
        from datetime import datetime

        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        crud.edit_gear_component(
            gear_component=_make_gc_update(id=1, retired_date=datetime(2024, 6, 1), active=True),
            user_id=1,
            db=mock_db,
        )
        assert db_gc.active is False

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_deactivate_without_retired_date(self, mock_db):
        # Regression: unchecking active with no retired date must persist
        # active=false; the client value is honoured, not overridden.
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        db_gc.active = True
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        crud.edit_gear_component(
            gear_component=_make_gc_update(id=1, retired_date=None, active=False),
            user_id=1,
            db=mock_db,
        )
        assert db_gc.active is False
        mock_db.commit.assert_called_once()

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_reactivate_by_clearing_retired_date(self, mock_db):
        # Clearing retired_date and sending active=true reactivates.
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = "some_date"
        db_gc.active = False
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        crud.edit_gear_component(
            gear_component=_make_gc_update(id=1, retired_date=None, active=True),
            user_id=1,
            db=mock_db,
        )
        assert db_gc.active is True
        mock_db.commit.assert_called_once()

    @patch("modules.gears.gear_components.crud._transform_gear_components", new=lambda x: x)
    def test_immutable_fields_ignored(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        setup_mock_execute(mock_db, return_one_or_none=db_gc)

        from pydantic import BaseModel

        class GCUpdate(BaseModel):
            id: int = 1
            user_id: int = 999
            gear_id: int = 999

        crud.edit_gear_component(gear_component=GCUpdate(), user_id=1, db=mock_db)
        assert db_gc.user_id != 999
        assert db_gc.gear_id != 999
        mock_db.commit.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        db_gc.id = 1
        db_gc.retired_date = None
        setup_mock_execute(mock_db, return_one_or_none=db_gc)
        mock_db.commit.side_effect = SQLAlchemyError("err")

        from pydantic import BaseModel

        class GCUpdate(BaseModel):
            id: int = 1
            brand: str = "SRAM"

        with pytest.raises(HTTPException) as e:
            crud.edit_gear_component(gear_component=GCUpdate(), user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestDeleteGearComponent:
    def test_success(self, mock_db):
        import modules.gears.gear_components.crud as crud
        import modules.gears.gear_components.models as m

        db_gc = MagicMock(spec=m.GearComponents)
        setup_mock_execute(mock_db, return_one_or_none=db_gc)
        crud.delete_gear_component(user_id=1, gear_component_id=1, db=mock_db)
        mock_db.delete.assert_called_once_with(db_gc)
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        import modules.gears.gear_components.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        with pytest.raises(HTTPException) as e:
            crud.delete_gear_component(user_id=1, gear_component_id=999, db=mock_db)
        assert e.value.status_code == 404

    def test_db_error(self, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_gear_component(user_id=1, gear_component_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetComponentsActivityStats:
    @patch("modules.gears.gear_components.crud.activities_integration")
    def test_success(self, mock_activities, mock_db):
        import modules.activities.activity.contracts as activities_contracts
        import modules.gears.gear_components.crud as crud

        comp1 = MagicMock(id=1, purchase_date=date(2024, 1, 1), retired_date=None)
        comp2 = MagicMock(id=2, purchase_date=date(2024, 6, 1), retired_date=date(2024, 9, 1))
        mock_db.execute.return_value.all.return_value = [comp1, comp2]
        mock_activities.get_gear_usage_totals_by_window.return_value = {
            1: activities_contracts.ActivityUsageTotals(distance=10000.0, time=3600.0),
            2: activities_contracts.ActivityUsageTotals(distance=5000.0, time=1800.0),
        }

        r = crud.get_components_activity_stats(gear_id=1, db=mock_db)

        assert r == {
            1: {"distance": 10000.0, "time": 3600.0},
            2: {"distance": 5000.0, "time": 1800.0},
        }
        # Each component becomes one window; the activities module owns the join.
        windows = mock_activities.get_gear_usage_totals_by_window.call_args.args[1]
        assert [w.key for w in windows] == [1, 2]
        assert windows[0].end_date is None
        assert windows[1].end_date == date(2024, 9, 1)

    @patch("modules.gears.gear_components.crud.activities_integration")
    def test_empty(self, mock_activities, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.return_value.all.return_value = []
        mock_activities.get_gear_usage_totals_by_window.return_value = {}
        r = crud.get_components_activity_stats(gear_id=1, db=mock_db)
        assert r == {}

    def test_db_error(self, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_components_activity_stats(gear_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestComponentWindowIsLocal:
    """The purchase/retired window is a calendar range, not an instant range.

    ``purchase_date``/``retired_date`` are dates, so comparing them against the
    raw ``start_time`` instant put the boundary at UTC midnight: at UTC-8 an
    evening ride the day *before* a purchase counted towards the new component,
    and at UTC+13 a morning ride *on* the purchase day did not count at all.

    The aggregation itself now lives in the activities module, which owns the
    local-date rule — see
    ``tests/activities/activity/test_crud.py::TestSumGearUsageByWindow``. What is
    still this module's responsibility is handing over the component bounds
    unchanged, which is asserted here.
    """

    @patch("modules.gears.gear_components.crud.activities_integration")
    def test_component_bounds_are_passed_through_as_calendar_dates(self, mock_activities):
        import modules.gears.gear_components.crud as crud

        db = MagicMock()
        db.execute.return_value.all.return_value = [
            MagicMock(id=7, purchase_date=date(2024, 3, 4), retired_date=date(2024, 5, 6)),
        ]
        mock_activities.get_gear_usage_totals_by_window.return_value = {}

        crud.get_components_activity_stats(gear_id=1, db=db)

        window = mock_activities.get_gear_usage_totals_by_window.call_args.args[1][0]
        assert window.start_date == date(2024, 3, 4)
        assert window.end_date == date(2024, 5, 6)
