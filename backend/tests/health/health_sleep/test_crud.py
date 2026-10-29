from datetime import date as datetime_date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema

pytestmark = pytest.mark.usefixtures("passthrough_serializers")


def _row(record_id: int = 1, seconds: int = 28800) -> MagicMock:
    row = MagicMock(spec=health_sleep_models.HealthSleep)
    row.id = record_id
    row.version = 1
    row.user_id = 1
    row.total_sleep_seconds = seconds
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 5

        assert health_sleep_crud.get_health_sleep_number_by_user_id(1, mock_db) == 5

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_sleep_crud.get_health_sleep_number_by_user_id(1, mock_db, datetime_date(2024, 1, 1))

        assert "health_sleep.date >=" in str(mock_db.execute.call_args.args[0])

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_sleep_crud.get_health_sleep_by_user_id(1, mock_db, 2, 10, datetime_date(2024, 1, 1))

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_sleep.date >=" in compiled

    def test_list_empty(self, mock_db):
        _returns_scalars(mock_db, [])

        assert health_sleep_crud.get_health_sleep_by_user_id(1, mock_db) == []

    def test_by_date_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(1, "2024-01-15", mock_db).id == 1

    def test_by_date_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(1, "2024-01-15", mock_db) is None


class TestCreateHealthSleep:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_sleep_schema.HealthSleepCreate(
            date=datetime_date(2024, 1, 15), total_sleep_seconds=28800, sleep_score_overall=85
        )

        with stub_model(health_sleep_crud, _row()) as model:
            health_sleep_crud.create_health_sleep(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        assert model.call_args.kwargs["total_sleep_seconds"] == 28800
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_date_is_a_conflict(self, mock_db, stub_model):
        mock_db.flush.side_effect = IntegrityError("duplicate", None, None)
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        with (
            stub_model(health_sleep_crud, _row()),
            pytest.raises(core_exceptions.ConflictError, match="Duplicate entry error"),
        ):
            health_sleep_crud.create_health_sleep(1, record, mock_db)


class TestEditHealthSleep:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_sleep_schema.HealthSleepUpdate(date=datetime_date(2024, 1, 15), total_sleep_seconds=32400)

        health_sleep_crud.edit_health_sleep(1, 1, update, mock_db, if_match="*")

        assert row.total_sleep_seconds == 32400
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_sleep_schema.HealthSleepUpdate(date=datetime_date(2024, 1, 15), total_sleep_seconds=32400)

        with pytest.raises(core_exceptions.NotFoundError, match="Health sleep not found"):
            health_sleep_crud.edit_health_sleep(1, 9, update, mock_db, if_match="*")


class TestDeleteHealthSleep:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_sleep_crud.delete_health_sleep(1, 1, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_crud.delete_health_sleep(1, 9, mock_db, if_match="*")
        mock_db.delete.assert_not_called()
