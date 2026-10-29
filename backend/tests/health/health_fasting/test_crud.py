from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema

pytestmark = pytest.mark.usefixtures("passthrough_serializers")


def _row(record_id: int = 1) -> MagicMock:
    row = MagicMock(spec=health_fasting_models.HealthFasting)
    row.id = record_id
    row.version = 1
    row.user_id = 1
    row.status = "in_progress"
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 4

        assert health_fasting_crud.get_health_fasting_number_by_user_id(1, mock_db) == 4

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_fasting_crud.get_health_fasting_number_by_user_id(1, mock_db, date(2024, 1, 1))

        assert "health_fasting.fast_start_time >=" in str(mock_db.execute.call_args.args[0])

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_fasting_crud.get_health_fasting_by_user_id(1, mock_db, 2, 10, date(2024, 1, 1))

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_fasting.fast_start_time >=" in compiled

    def test_by_id_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_fasting_crud.get_health_fasting_by_id_and_user_id(1, 1, mock_db).id == 1

    def test_by_id_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_fasting_crud.get_health_fasting_by_id_and_user_id(9, 1, mock_db) is None

    def test_active_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_fasting_crud.get_active_fasting_by_user_id(1, mock_db).status == "in_progress"

    def test_active_none(self, mock_db):
        _returns_one(mock_db, None)

        assert health_fasting_crud.get_active_fasting_by_user_id(1, mock_db) is None


class TestAggregates:
    def test_completed_count(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 7

        assert health_fasting_crud.get_completed_fasting_count(1, mock_db) == 7

    def test_total_seconds_defaults_to_zero(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = None

        assert health_fasting_crud.get_total_fasting_seconds(1, mock_db) == 0

    def test_average_is_truncated_to_seconds(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3600.7

        assert health_fasting_crud.get_avg_fasting_duration(1, mock_db) == 3600

    def test_average_is_none_without_data(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = None

        assert health_fasting_crud.get_avg_fasting_duration(1, mock_db) is None

    def test_completed_dates_are_bucketed_in_the_given_timezone(self, mock_db):
        _returns_scalars(mock_db, [date(2024, 1, 14), date(2024, 1, 15)])

        result = health_fasting_crud.get_completed_fasting_dates_by_user_id(1, "Asia/Tokyo", mock_db)

        assert result == [date(2024, 1, 14), date(2024, 1, 15)]
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "Asia/Tokyo" in compiled


class TestCreateHealthFasting:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with stub_model(health_fasting_crud, _row()) as model:
            health_fasting_crud.create_health_fasting(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_integrity_error_is_a_conflict(self, mock_db, stub_model):
        mock_db.flush.side_effect = IntegrityError("constraint", None, None)
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with (
            stub_model(health_fasting_crud, _row()),
            pytest.raises(core_exceptions.ConflictError),
        ):
            health_fasting_crud.create_health_fasting(1, record, mock_db)


class TestEditHealthFasting:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_fasting_schema.HealthFastingUpdate(notes="felt good")

        health_fasting_crud.edit_health_fasting(1, 1, update, mock_db, if_match="*")

        assert row.notes == "felt good"
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_a_second_active_fast_is_a_conflict(self, mock_db):
        _returns_one(mock_db, _row())
        mock_db.flush.side_effect = IntegrityError("constraint", None, None)
        update = health_fasting_schema.HealthFastingUpdate(status="in_progress")

        with pytest.raises(core_exceptions.ConflictError):
            health_fasting_crud.edit_health_fasting(1, 1, update, mock_db, if_match="*")

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_fasting_schema.HealthFastingUpdate(notes="x")

        with pytest.raises(core_exceptions.NotFoundError, match="Health fasting not found"):
            health_fasting_crud.edit_health_fasting(1, 9, update, mock_db, if_match="*")


class TestEndHealthFasting:
    def test_a_stale_version_is_refused(self, mock_db):
        row = _row()
        row.version = 4
        _returns_one(mock_db, row)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_fasting_crud.end_health_fasting(
                1, 1, datetime(2024, 1, 16, 8, 0, 0), "completed", 86400, None, mock_db, if_match='"3"'
            )

        mock_db.flush.assert_not_called()

    def test_stages_the_end_fields(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        end = datetime(2024, 1, 16, 8, 0, 0)

        health_fasting_crud.end_health_fasting(1, 1, end, "completed", 86400, "done", mock_db, if_match="*")

        assert (row.fast_end_time, row.status, row.actual_duration_seconds, row.notes) == (
            end,
            "completed",
            86400,
            "done",
        )
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_keeps_existing_notes_when_none_are_given(self, mock_db):
        row = _row()
        row.notes = "before"
        _returns_one(mock_db, row)

        health_fasting_crud.end_health_fasting(1, 1, datetime(2024, 1, 16), "broken", 10, None, mock_db, if_match="*")

        assert row.notes == "before"

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_crud.end_health_fasting(
                1, 9, datetime(2024, 1, 16), "broken", 10, None, mock_db, if_match="*"
            )


class TestDeleteHealthFasting:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_fasting_crud.delete_health_fasting(1, 1, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_crud.delete_health_fasting(1, 9, mock_db, if_match="*")
        mock_db.delete.assert_not_called()
