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
    def test_success(self, mock_db):
        import modules.gears.gear_components.crud as crud

        row1 = MagicMock()
        row1.comp_id = 1
        row1.distance = 10000.0
        row1.time = 3600.0
        row2 = MagicMock()
        row2.comp_id = 2
        row2.distance = 5000.0
        row2.time = 1800.0
        mock_db.execute.return_value.all.return_value = [row1, row2]

        r = crud.get_components_activity_stats(gear_id=1, db=mock_db)
        assert r == {
            1: {"distance": 10000.0, "time": 3600.0},
            2: {"distance": 5000.0, "time": 1800.0},
        }

    def test_empty(self, mock_db):
        import modules.gears.gear_components.crud as crud

        mock_db.execute.return_value.all.return_value = []
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
    """

    @staticmethod
    def _emitted_sql(gear_id: int = 1) -> str:
        # Compiling an ORM statement configures the whole mapper registry, and
        # relationships use string targets — so every related model has to be
        # imported first or the compile fails on an unresolved name.
        import modules.gears.gear_components.crud as crud
        from tests._helpers.db import _import_all_models

        _import_all_models()

        db = MagicMock()
        db.get_bind.return_value.dialect.name = "postgresql"
        db.execute.return_value.all.return_value = []

        crud.get_components_activity_stats(gear_id=gear_id, db=db)

        from sqlalchemy.dialects import postgresql

        statement = db.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    def test_window_compares_the_activitys_local_date(self):
        sql = self._emitted_sql()

        # The activity side of the join is converted through its own IANA zone
        # and truncated to a date before being compared to the component bounds.
        assert "coalesce(activities.timezone, 'UTC')" in sql
        assert "date(timezone(" in sql

    def test_window_does_not_compare_the_raw_instant(self):
        """The regression itself: a bare ``start_time`` bound is the UTC-midnight bug."""
        sql = self._emitted_sql().replace("\n", " ")

        assert ">= anon_1.purchase_date" in sql
        # ``start_time`` may only appear wrapped in the timezone conversion.
        assert "activities.start_time >=" not in sql
        assert "activities.start_time <=" not in sql

    def test_retired_date_is_inclusive_and_nullable(self):
        """A component still in use has no upper bound; one retired today keeps that day."""
        sql = self._emitted_sql().replace("\n", " ")

        assert "anon_1.retired_date IS NULL" in sql
        assert "<= anon_1.retired_date" in sql
