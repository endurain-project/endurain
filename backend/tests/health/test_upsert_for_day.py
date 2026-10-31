from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.constants as health_constants


def _record(record_id: int = 7):
    return SimpleNamespace(id=record_id)


class TestUpsertForDay:
    def test_creates_the_record_when_the_day_has_none(self, mock_db):
        created = _record(1)
        edit = MagicMock()

        result = health_computation.upsert_for_day(lambda: None, lambda: created, edit, mock_db)

        assert result is created
        edit.assert_not_called()

    def test_edits_the_record_the_day_already_has(self, mock_db):
        existing, edited = _record(7), _record(7)
        create = MagicMock()
        edit = MagicMock(return_value=edited)

        result = health_computation.upsert_for_day(lambda: existing, create, edit, mock_db)

        assert result is edited
        edit.assert_called_once_with(7)
        create.assert_not_called()

    def test_a_writer_that_created_the_day_first_is_updated_instead(self, mock_db):
        winner, edited = _record(9), _record(9)
        finds = iter([None, winner])
        create = MagicMock(side_effect=core_exceptions.ConflictError("duplicate"))
        edit = MagicMock(return_value=edited)

        result = health_computation.upsert_for_day(lambda: next(finds), create, edit, mock_db)

        assert result is edited
        edit.assert_called_once_with(9)

    def test_a_conflict_with_no_record_to_find_is_raised(self, mock_db):
        create = MagicMock(side_effect=core_exceptions.ConflictError("duplicate"))

        with pytest.raises(core_exceptions.ConflictError):
            health_computation.upsert_for_day(lambda: None, create, MagicMock(), mock_db)

    def test_a_row_changed_under_the_edit_is_read_again_and_retried(self, mock_db):
        edit = MagicMock(side_effect=[StaleDataError("moved"), _record(7)])

        health_computation.upsert_for_day(lambda: _record(7), MagicMock(), edit, mock_db)

        assert edit.call_count == 2

    def test_a_row_that_keeps_moving_is_given_up_on(self, mock_db):
        edit = MagicMock(side_effect=StaleDataError("moved"))

        with pytest.raises(StaleDataError):
            health_computation.upsert_for_day(lambda: _record(7), MagicMock(), edit, mock_db)

        assert edit.call_count == health_constants.UPSERT_ATTEMPTS

    def test_a_row_deleted_between_attempts_is_raised(self, mock_db):
        finds = iter([_record(7), None])
        edit = MagicMock(side_effect=StaleDataError("moved"))

        with pytest.raises(StaleDataError):
            health_computation.upsert_for_day(lambda: next(finds), MagicMock(), edit, mock_db)
