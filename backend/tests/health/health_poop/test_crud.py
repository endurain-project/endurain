from datetime import date as datetime_date
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema

pytestmark = pytest.mark.usefixtures("passthrough_serializers")


def _row(record_id: int = 1) -> MagicMock:
    row = MagicMock(spec=health_poop_models.HealthPoop)
    row.id = record_id
    row.version = 1
    row.user_id = 1
    row.date_time = datetime(2024, 1, 15, 10, 0, 0)
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 4

        assert health_poop_crud.get_health_poop_number_by_user_id(1, mock_db) == 4

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_poop_crud.get_health_poop_number_by_user_id(1, mock_db, datetime_date(2024, 1, 1), "Asia/Tokyo")

        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "Asia/Tokyo" in compiled
        assert ">=" in compiled

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_poop_crud.get_health_poop_by_user_id(1, mock_db, 2, 10, datetime_date(2024, 1, 1), "Asia/Tokyo")

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "Asia/Tokyo" in compiled

    def test_by_id_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_poop_crud.get_health_poop_by_id_and_user_id(1, 1, mock_db).id == 1

    def test_by_id_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_poop_crud.get_health_poop_by_id_and_user_id(9, 1, mock_db) is None

    def test_by_date_resolves_the_day_in_the_given_timezone(self, mock_db):
        _returns_scalars(mock_db, [_row(), _row(2)])

        result = health_poop_crud.get_health_poop_by_date_and_user_id(1, "2024-01-15", "Asia/Tokyo", mock_db)

        assert len(result) == 2
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "Asia/Tokyo" in compiled


class TestCreateHealthPoop:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_poop_schema.HealthPoopCreate(date_time=datetime(2024, 1, 15, 10, 0, 0))

        with stub_model(health_poop_crud, _row()) as model:
            health_poop_crud.create_health_poop(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_integrity_error_is_a_conflict(self, mock_db, stub_model):
        mock_db.flush.side_effect = IntegrityError("constraint", None, None)
        record = health_poop_schema.HealthPoopCreate(date_time=datetime(2024, 1, 15, 10, 0, 0))

        with (
            stub_model(health_poop_crud, _row()),
            pytest.raises(core_exceptions.ConflictError),
        ):
            health_poop_crud.create_health_poop(1, record, mock_db)


class TestEditHealthPoop:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_poop_schema.HealthPoopUpdate(notes="ok")

        health_poop_crud.edit_health_poop(1, 1, update, mock_db, if_match="*")

        assert row.notes == "ok"
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_poop_schema.HealthPoopUpdate(notes="ok")

        with pytest.raises(core_exceptions.NotFoundError, match="Health poop not found"):
            health_poop_crud.edit_health_poop(1, 9, update, mock_db, if_match="*")


class TestDeleteHealthPoop:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_poop_crud.delete_health_poop(1, 1, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_crud.delete_health_poop(1, 9, mock_db, if_match="*")
        mock_db.delete.assert_not_called()
