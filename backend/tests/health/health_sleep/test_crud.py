import uuid
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema

pytestmark = pytest.mark.usefixtures("passthrough_serializers")


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ID = uuid.uuid4()
_OTHER_ID = uuid.uuid4()


def _row(record_id: uuid.UUID = _ID, seconds: int = 28800) -> MagicMock:
    row = MagicMock(spec=health_sleep_models.HealthSleep)
    row.id = record_id
    row.version = 1
    row.user_id = _USER_ID
    row.total_sleep_seconds = seconds
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 5

        assert health_sleep_crud.get_health_sleep_number_by_user_id(_USER_ID, mock_db) == 5

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_sleep_crud.get_health_sleep_number_by_user_id(_USER_ID, mock_db, datetime_date(2024, 1, 1))

        assert "health_sleep.date >=" in str(mock_db.execute.call_args.args[0])

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_sleep_crud.get_health_sleep_list_items_by_user_id(
            _USER_ID, mock_db, 2, 10, datetime_date(2024, 1, 1)
        )

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_sleep.date >=" in compiled

    def test_the_list_reads_rows_as_list_items_and_the_export_as_full_records(self, mock_db):
        _returns_scalars(mock_db, [])
        with patch.object(health_computation, "to_read_schemas", return_value=[]) as convert:
            health_sleep_crud.get_health_sleep_list_items_by_user_id(_USER_ID, mock_db)
            health_sleep_crud.get_health_sleep_by_user_id(_USER_ID, mock_db)

        assert [call.args[0] for call in convert.call_args_list] == [
            health_sleep_schema.HealthSleepListItem,
            health_sleep_schema.HealthSleepRead,
        ]

    def test_the_resting_heart_rate_filter_bounds_the_count_and_the_page(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 0
        health_sleep_crud.get_health_sleep_number_by_user_id(_USER_ID, mock_db, has_resting_heart_rate=True)
        assert "health_sleep.resting_heart_rate IS NOT NULL" in str(mock_db.execute.call_args.args[0])

        _returns_scalars(mock_db, [])
        health_sleep_crud.get_health_sleep_list_items_by_user_id(_USER_ID, mock_db, has_resting_heart_rate=False)
        assert "health_sleep.resting_heart_rate IS NULL" in str(mock_db.execute.call_args.args[0])

    def test_no_resting_heart_rate_filter_by_default(self, mock_db):
        _returns_scalars(mock_db, [])

        health_sleep_crud.get_health_sleep_list_items_by_user_id(_USER_ID, mock_db)

        assert "resting_heart_rate" not in str(mock_db.execute.call_args.args[0]).split("WHERE", 1)[1]

    def test_list_empty(self, mock_db):
        _returns_scalars(mock_db, [])

        assert health_sleep_crud.get_health_sleep_list_items_by_user_id(_USER_ID, mock_db) == []

    def test_by_date_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(_USER_ID, "2024-01-15", mock_db).id == _ID

    def test_by_date_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(_USER_ID, "2024-01-15", mock_db) is None


class TestCreateHealthSleep:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_sleep_schema.HealthSleepCreate(
            date=datetime_date(2024, 1, 15), total_sleep_seconds=28800, sleep_score_overall=85
        )

        with stub_model(health_sleep_crud, _row()) as model:
            health_sleep_crud.create_health_sleep(_USER_ID, record, mock_db)

        assert model.call_args.kwargs["user_id"] == _USER_ID
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
            health_sleep_crud.create_health_sleep(_USER_ID, record, mock_db)


class TestEditHealthSleep:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_sleep_schema.HealthSleepUpdate(date=datetime_date(2024, 1, 15), total_sleep_seconds=32400)

        health_sleep_crud.edit_health_sleep(_USER_ID, _ID, update, mock_db, if_match="*")

        assert row.total_sleep_seconds == 32400
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_sleep_schema.HealthSleepUpdate(date=datetime_date(2024, 1, 15), total_sleep_seconds=32400)

        with pytest.raises(core_exceptions.NotFoundError, match="Health sleep not found"):
            health_sleep_crud.edit_health_sleep(_USER_ID, _OTHER_ID, update, mock_db, if_match="*")


class TestDeleteHealthSleep:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_sleep_crud.delete_health_sleep(_USER_ID, _ID, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_crud.delete_health_sleep(_USER_ID, _OTHER_ID, mock_db, if_match="*")
        mock_db.delete.assert_not_called()


class TestById:
    def test_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_sleep_crud.get_health_sleep_by_id(_USER_ID, _ID, mock_db).id == _ID

    def test_missing_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError, match="Health sleep not found"):
            health_sleep_crud.get_health_sleep_by_id(_USER_ID, _OTHER_ID, mock_db)
