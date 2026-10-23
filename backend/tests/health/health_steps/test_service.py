from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.service as health_steps_service

_PREFIX = "modules.health.health_steps.service"


class TestStageEdit:
    def test_rejects_a_record_of_another_user(self, mock_db):
        record = health_steps_schema.HealthStepsUpdate(id=1, user_id=2, date=datetime_date(2024, 1, 15), steps=1)

        with pytest.raises(core_exceptions.PermissionDeniedError):
            health_steps_service.stage_edit_health_steps(1, record, mock_db)

    @patch(f"{_PREFIX}.health_steps_crud.edit_health_steps")
    def test_stages_without_committing(self, mock_edit, mock_db):
        record = health_steps_schema.HealthStepsUpdate(id=1, user_id=1, date=datetime_date(2024, 1, 15), steps=1)

        health_steps_service.stage_edit_health_steps(1, record, mock_db)

        mock_edit.assert_called_once_with(1, record, mock_db)
        mock_db.commit.assert_not_called()


class TestCreateHealthSteps:
    @patch(f"{_PREFIX}.health_steps_crud.create_health_steps")
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_date_and_user_id", return_value=None)
    def test_creates_and_commits_when_the_date_is_free(self, _get_by_date, mock_create, mock_db):
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        result = health_steps_service.create_health_steps(1, record, mock_db)

        assert result is mock_create.return_value
        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_steps_crud.edit_health_steps")
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_date_and_user_id")
    def test_edits_the_existing_record_of_the_date(self, mock_get_by_date, mock_edit, mock_db):
        mock_get_by_date.return_value = MagicMock(id=7)
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        health_steps_service.create_health_steps(1, record, mock_db)

        edited = mock_edit.call_args.args[1]
        assert (edited.id, edited.user_id) == (7, 1)
        mock_db.commit.assert_called_once()


class TestRaceForTheDate:
    @patch(f"{_PREFIX}.health_steps_crud.edit_health_steps")
    @patch(f"{_PREFIX}.health_steps_crud.create_health_steps", side_effect=core_exceptions.ConflictError("duplicate"))
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_date_and_user_id")
    def test_a_record_that_lost_the_race_updates_the_one_that_won(self, mock_get_by_date, _create, mock_edit, mock_db):
        mock_get_by_date.side_effect = [None, MagicMock(id=7)]
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        health_steps_service.create_health_steps(1, record, mock_db)

        assert mock_edit.call_args.args[1].id == 7
        mock_db.begin_nested.assert_called_once()

    @patch(f"{_PREFIX}.health_steps_crud.create_health_steps", side_effect=core_exceptions.ConflictError("duplicate"))
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_date_and_user_id", return_value=None)
    def test_a_conflict_with_no_record_to_update_is_raised(self, _get_by_date, _create, mock_db):
        record = health_steps_schema.HealthStepsCreate(date=datetime_date(2024, 1, 15), steps=9000)

        with pytest.raises(core_exceptions.ConflictError):
            health_steps_service.create_health_steps(1, record, mock_db)


class TestEditAndDelete:
    @patch(f"{_PREFIX}.health_steps_crud.edit_health_steps")
    def test_edit_commits(self, mock_edit, mock_db):
        record = health_steps_schema.HealthStepsUpdate(id=1, user_id=1, date=datetime_date(2024, 1, 15), steps=1)

        health_steps_service.edit_health_steps(1, record, mock_db)

        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_steps_crud.delete_health_steps")
    def test_delete_commits(self, mock_delete, mock_db):
        health_steps_service.delete_health_steps(1, 5, mock_db)

        mock_delete.assert_called_once_with(1, 5, mock_db)
        mock_db.commit.assert_called_once()


class TestListHealthSteps:
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_steps_service.list_health_steps(1, mock_db, 2, 10, health_constants.Interval.LAST_30_DAYS)

        since = datetime_date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since)
        assert (result.total, result.page_number, result.num_records) == (0, 2, 10)

    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_steps_service.list_health_steps(1, mock_db)

        mock_number.assert_called_once_with(1, mock_db, None)


class TestMissingDate:
    @patch(f"{_PREFIX}.health_steps_crud.create_health_steps")
    @patch(f"{_PREFIX}.health_steps_crud.get_health_steps_by_date_and_user_id", return_value=None)
    @patch(f"{_PREFIX}.core_timezone.today_in", return_value=datetime_date(2024, 1, 15))
    def test_defaults_to_today_in_the_servers_timezone(self, _today, _get_by_date, mock_create, mock_db):
        record = health_steps_schema.HealthStepsCreate(steps=9000)

        health_steps_service.create_health_steps(1, record, mock_db)

        assert mock_create.call_args.args[1].date == datetime_date(2024, 1, 15)
