import uuid
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.service as health_water_service

_PREFIX = "modules.health.health_water.service"

_NO_RANGE = core_date_range.DateRange()


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ID = uuid.uuid4()
_OTHER_ID = uuid.uuid4()


def _update() -> health_water_schema.HealthWaterUpdate:
    return health_water_schema.HealthWaterUpdate(date=datetime_date(2024, 1, 15), amount_ml=900.0)


class TestStageEdit:
    @patch(f"{_PREFIX}.health_water_crud.edit_health_water")
    def test_stages_without_committing(self, mock_edit, mock_db):
        record = _update()

        health_water_service.stage_edit_health_water(_USER_ID, _ID, record, mock_db, if_match="*")

        mock_edit.assert_called_once_with(_USER_ID, _ID, record, mock_db, if_match="*")
        mock_db.commit.assert_not_called()


class TestCreateHealthWater:
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    @patch(f"{_PREFIX}.health_water_crud.create_health_water")
    def test_creates_and_commits_when_the_date_is_free(self, mock_create, _today, mock_db, caplog):
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=500.0)

        with caplog.at_level("DEBUG", logger=health_water_service.logger.name):
            result = health_water_service.create_health_water(_USER_ID, record, mock_db)

        assert result is mock_create.return_value
        mock_db.commit.assert_called_once()
        # A completed state change, reported as the other modules report theirs.
        assert [record.levelname for record in caplog.records] == ["INFO"]

    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    @patch(f"{_PREFIX}.health_water_crud.create_health_water", side_effect=core_exceptions.ConflictError("duplicate"))
    def test_a_second_entry_for_the_day_is_a_conflict_and_adds_nothing(self, _create, _today, mock_db):
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=250.0)

        with pytest.raises(core_exceptions.ConflictError):
            health_water_service.create_health_water(_USER_ID, record, mock_db)

        mock_db.commit.assert_not_called()

    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    @patch(f"{_PREFIX}.health_water_crud.create_health_water")
    def test_a_future_date_is_refused(self, mock_create, _today, mock_db):
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 16), amount_ml=250.0)

        with pytest.raises(core_exceptions.InvalidInputError):
            health_water_service.create_health_water(_USER_ID, record, mock_db)

        mock_create.assert_not_called()


class TestEditAndDelete:
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    @patch(f"{_PREFIX}.health_water_crud.edit_health_water")
    def test_edit_commits(self, mock_edit, _today, mock_db):
        health_water_service.edit_health_water(_USER_ID, _ID, _update(), mock_db, if_match="*")

        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_water_crud.delete_health_water")
    def test_delete_commits(self, mock_delete, mock_db):
        health_water_service.delete_health_water(_USER_ID, _ID, mock_db, if_match="*")

        mock_delete.assert_called_once_with(_USER_ID, _ID, mock_db, if_match="*")
        mock_db.commit.assert_called_once()


class TestListHealthWater:
    @patch(f"{_PREFIX}.health_water_crud.get_health_water_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_water_crud.get_health_water_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_water_service.list_health_water(
            _USER_ID,
            mock_db,
            page_number=2,
            num_records=10,
            interval=health_constants.Interval.LAST_30_DAYS,
            date_range=_NO_RANGE,
        )

        since = datetime_date(2023, 12, 16)
        mock_number.assert_called_once_with(_USER_ID, mock_db, since, None)
        mock_list.assert_called_once_with(_USER_ID, mock_db, 2, 10, since, None)
        assert (result.total, result.page, result.num_records) == (0, 2, 10)

    @patch(f"{_PREFIX}.health_water_crud.get_health_water_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_water_crud.get_health_water_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_water_service.list_health_water(_USER_ID, mock_db, date_range=_NO_RANGE)

        mock_number.assert_called_once_with(_USER_ID, mock_db, None, None)


class TestMissingDate:
    @patch(f"{_PREFIX}.health_water_crud.create_health_water")
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_defaults_to_the_athletes_local_today(self, mock_today, mock_create, mock_db):
        record = health_water_schema.HealthWaterCreate(amount_ml=500.0)

        health_water_service.create_health_water(_USER_ID, record, mock_db)

        assert mock_create.call_args.args[1].date == datetime_date(2024, 1, 15)
        mock_today.assert_called_once_with(_USER_ID, mock_db)


class TestStageUpsertHealthWater:
    @patch(f"{_PREFIX}.health_water_crud.edit_health_water")
    @patch(f"{_PREFIX}.health_water_crud.get_health_water_by_date_and_user_id")
    def test_replaces_the_amount_of_the_date_instead_of_adding_to_it(self, mock_get_by_date, mock_edit, mock_db):
        mock_get_by_date.return_value = MagicMock(id=_ID)
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=1500)

        health_water_service.stage_upsert_health_water(_USER_ID, record, mock_db)

        assert mock_edit.call_args.args[:2] == (_USER_ID, _ID)
        assert mock_edit.call_args.args[2].amount_ml == 1500
        mock_db.commit.assert_not_called()

    @patch(f"{_PREFIX}.health_water_crud.create_health_water")
    @patch(f"{_PREFIX}.health_water_crud.get_health_water_by_date_and_user_id", return_value=None)
    def test_creates_the_record_when_the_date_is_free(self, _get_by_date, mock_create, mock_db):
        record = health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=1500)

        result = health_water_service.stage_upsert_health_water(_USER_ID, record, mock_db)

        assert result is mock_create.return_value
