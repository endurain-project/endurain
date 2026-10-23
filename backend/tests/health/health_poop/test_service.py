from datetime import date as datetime_date
from datetime import datetime
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service

_PREFIX = "modules.health.health_poop.service"


class TestGetHealthPoop:
    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_by_id_and_user_id")
    def test_returns_the_record(self, mock_get, mock_db):
        assert health_poop_service.get_health_poop(1, 5, mock_db) is mock_get.return_value
        mock_get.assert_called_once_with(5, 1, mock_db)

    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_by_id_and_user_id", return_value=None)
    def test_missing_record_is_not_found(self, _get, mock_db):
        with pytest.raises(core_exceptions.NotFoundError, match="Poop record not found"):
            health_poop_service.get_health_poop(1, 5, mock_db)


class TestListByDate:
    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_by_date_and_user_id")
    @patch(f"{_PREFIX}.users_integration.resolve_timezone", return_value="Asia/Tokyo")
    def test_resolves_the_day_in_the_users_timezone(self, _tz, mock_get, mock_db):
        health_poop_service.list_health_poop_by_date(1, "2024-01-15", mock_db)

        mock_get.assert_called_once_with(1, "2024-01-15", "Asia/Tokyo", mock_db)


class TestWrites:
    @patch(f"{_PREFIX}.health_poop_crud.create_health_poop")
    def test_create_commits(self, mock_create, mock_db):
        record = health_poop_schema.HealthPoopCreate(date_time=datetime(2024, 1, 15, 10, 0, 0))

        assert health_poop_service.create_health_poop(1, record, mock_db) is mock_create.return_value
        mock_db.commit.assert_called_once()

    def test_edit_rejects_a_record_of_another_user(self, mock_db):
        with pytest.raises(core_exceptions.PermissionDeniedError):
            health_poop_service.edit_health_poop(1, health_poop_schema.HealthPoopUpdate(id=1, user_id=2), mock_db)
        mock_db.commit.assert_not_called()

    @patch(f"{_PREFIX}.health_poop_crud.edit_health_poop")
    def test_edit_commits(self, mock_edit, mock_db):
        health_poop_service.edit_health_poop(1, health_poop_schema.HealthPoopUpdate(id=1, user_id=1), mock_db)

        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_poop_crud.delete_health_poop")
    def test_delete_commits(self, mock_delete, mock_db):
        health_poop_service.delete_health_poop(1, 5, mock_db)

        mock_delete.assert_called_once_with(1, 5, mock_db)
        mock_db.commit.assert_called_once()


class TestListHealthPoop:
    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_poop_service.list_health_poop(1, mock_db, 2, 10, health_constants.Interval.LAST_30_DAYS)

        since = datetime_date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since)
        assert (result.total, result.page_number, result.num_records) == (0, 2, 10)

    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_poop_crud.get_health_poop_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_poop_service.list_health_poop(1, mock_db)

        mock_number.assert_called_once_with(1, mock_db, None)
