from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema


def _row(record_id: int = 1, steps: int = 10000) -> MagicMock:
    row = MagicMock(spec=health_steps_models.HealthSteps)
    row.id = record_id
    row.user_id = 1
    row.date = datetime_date(2024, 1, 15)
    row.steps = steps
    row.source = None
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestReads:
    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3

        assert health_steps_crud.get_health_steps_number_by_user_id(1, mock_db) == 3

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_steps_crud.get_health_steps_number_by_user_id(1, mock_db, datetime_date(2024, 1, 1))

        assert "health_steps.date >=" in str(mock_db.execute.call_args.args[0])

    def test_list_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_steps_crud.get_health_steps_by_user_id(1, mock_db, 2, 10, datetime_date(2024, 1, 1))

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_steps.date >=" in compiled

    def test_list_empty(self, mock_db):
        _returns_scalars(mock_db, [])

        assert health_steps_crud.get_health_steps_by_user_id(1, mock_db) == []

    def test_by_date_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_steps_crud.get_health_steps_by_date_and_user_id(1, "2024-01-15", mock_db).steps == 10000

    def test_by_date_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_steps_crud.get_health_steps_by_date_and_user_id(1, "2024-01-15", mock_db) is None


class TestCreateHealthSteps:
    def test_stages_without_committing(self, mock_db):
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        with patch.object(health_steps_models, "HealthSteps", return_value=_row()) as model:
            health_steps_crud.create_health_steps(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        assert model.call_args.kwargs["steps"] == 9000
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_date_is_a_conflict(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("duplicate", None, None)
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        with (
            patch.object(health_steps_models, "HealthSteps", return_value=_row()),
            pytest.raises(core_exceptions.ConflictError, match="Duplicate entry error"),
        ):
            health_steps_crud.create_health_steps(1, record, mock_db)


class TestEditHealthSteps:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_steps_schema.HealthStepsUpdate(id=1, user_id=1, date=datetime_date(2024, 1, 15), steps=12000)

        health_steps_crud.edit_health_steps(1, update, mock_db)

        assert row.steps == 12000
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_steps_schema.HealthStepsUpdate(id=9, user_id=1, date=datetime_date(2024, 1, 15), steps=12000)

        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_steps_crud.edit_health_steps(1, update, mock_db)


class TestDeleteHealthSteps:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_steps_crud.delete_health_steps(1, 1, mock_db)

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_steps_crud.delete_health_steps(1, 9, mock_db)
        mock_db.delete.assert_not_called()
