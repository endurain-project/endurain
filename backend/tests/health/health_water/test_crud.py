from datetime import date as datetime_date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.record_crud as health_record_crud

pytestmark = pytest.mark.usefixtures("passthrough_serializers")


def _row(record_id: int = 1, amount_ml: float = 500.0) -> MagicMock:
    row = MagicMock(spec=health_water_models.HealthWater)
    row.id = record_id
    row.version = 1
    row.user_id = 1
    row.amount_ml = amount_ml
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 4

        assert health_water_crud.get_health_water_number_by_user_id(1, mock_db) == 4

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_water_crud.get_health_water_number_by_user_id(1, mock_db, datetime_date(2024, 1, 1))

        assert "health_water.date >=" in str(mock_db.execute.call_args.args[0])

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_water_crud.get_health_water_by_user_id(1, mock_db, 2, 10, datetime_date(2024, 1, 1))

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_water.date >=" in compiled

    def test_by_date_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_water_crud.get_health_water_by_date_and_user_id(1, "2024-01-15", mock_db).id == 1

    def test_by_date_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_water_crud.get_health_water_by_date_and_user_id(1, "2024-01-15", mock_db) is None


class TestCreateHealthWater:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=500.0)

        with stub_model(health_water_crud, _row()) as model:
            health_water_crud.create_health_water(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        assert model.call_args.kwargs["amount_ml"] == 500.0
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_date_is_a_conflict(self, mock_db, stub_model):
        mock_db.flush.side_effect = IntegrityError("duplicate", None, None)
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=500.0)

        with (
            stub_model(health_water_crud, _row()),
            pytest.raises(core_exceptions.ConflictError, match="Duplicate entry error"),
        ):
            health_water_crud.create_health_water(1, record, mock_db)


class TestEditHealthWater:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_water_schema.HealthWaterUpdate(date=datetime_date(2024, 1, 15), amount_ml=900.0)

        health_water_crud.edit_health_water(1, 1, update, mock_db, if_match="*")

        assert row.amount_ml == 900.0
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_water_schema.HealthWaterUpdate(date=datetime_date(2024, 1, 15), amount_ml=900.0)

        with pytest.raises(core_exceptions.NotFoundError, match="Health water not found"):
            health_water_crud.edit_health_water(1, 9, update, mock_db, if_match="*")


class TestDeleteHealthWater:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_water_crud.delete_health_water(1, 1, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_water_crud.delete_health_water(1, 9, mock_db, if_match="*")
        mock_db.delete.assert_not_called()


class TestAddHealthWaterAmount:
    @patch.object(health_record_crud, "get_owned")
    def test_adds_in_one_update_and_returns_the_refreshed_record(self, mock_get_model, mock_db):
        mock_get_model.return_value = _row(7)

        result = health_water_crud.add_health_water_amount(1, 7, Decimal(250), "web", mock_db)

        mock_db.execute.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_get_model.return_value)
        assert result is mock_get_model.return_value
