from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.record_crud as health_record_crud

_SPEC = health_record_crud.RecordSpec(
    model=health_steps_models.HealthSteps,
    read_schema=health_steps_schema.HealthStepsRead,
    not_found="Health steps not found",
    etag_label="steps record",
)


def _row(version: int = 1) -> MagicMock:
    row = MagicMock(spec=health_steps_models.HealthSteps)
    row.version = version
    return row


class TestGetOwned:
    def test_returns_the_row(self, mock_db):
        row = _row()
        mock_db.execute.return_value.scalar_one_or_none.return_value = row

        assert health_record_crud.get_owned(_SPEC, 1, 2, mock_db) is row

    def test_a_missing_row_is_not_found_with_the_spec_message(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_crud.get_owned(_SPEC, 1, 2, mock_db)


class TestSave:
    def test_flushes_refreshes_and_serializes(self, mock_db, passthrough_serializers):
        row = _row()

        assert health_record_crud.save(_SPEC, row, mock_db) is row
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(row)

    def test_a_constraint_violation_is_the_given_conflict(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("x", None, None)

        with pytest.raises(core_exceptions.ConflictError, match="taken"):
            health_record_crud.save(_SPEC, _row(), mock_db, conflict="taken")

    def test_without_a_conflict_the_integrity_error_is_not_translated(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("x", None, None)

        with pytest.raises(IntegrityError):
            health_record_crud.save(_SPEC, _row(), mock_db)


class TestEditRow:
    def test_a_stale_version_is_refused_before_anything_changes(self, mock_db):
        row = _row(version=3)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_record_crud.edit_row(
                _SPEC, row, health_steps_schema.HealthStepsUpdate(steps=5), mock_db, if_match='"2"'
            )

        mock_db.flush.assert_not_called()

    def test_only_the_set_fields_are_applied(self, mock_db, passthrough_serializers):
        row = _row(version=3)

        health_record_crud.edit_row(_SPEC, row, health_steps_schema.HealthStepsUpdate(steps=5), mock_db, if_match="*")

        assert row.steps == 5


class TestDelete:
    def test_the_named_version_deletes_the_row(self, mock_db):
        row = _row(version=3)
        mock_db.execute.return_value.scalar_one_or_none.return_value = row

        health_record_crud.delete(_SPEC, 1, 2, mock_db, if_match='"3"')

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()

    def test_a_stale_version_is_refused_and_nothing_is_deleted(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = _row(version=4)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_record_crud.delete(_SPEC, 1, 2, mock_db, if_match='"3"')
        mock_db.delete.assert_not_called()

    def test_a_missing_row_is_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            health_record_crud.delete(_SPEC, 1, 2, mock_db, if_match='"3"')


def test_the_duplicate_date_message_names_the_day():
    assert health_record_crud.duplicate_date_message(date(2024, 1, 15)).endswith("created for 2024-01-15")
