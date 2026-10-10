from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema


class TestGetHealthFastingNumber:
    def test_success(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 5
        result = health_fasting_crud.get_health_fasting_number_by_user_id(1, mock_db)
        assert result == 5

    def test_zero(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 0
        result = health_fasting_crud.get_health_fasting_number_by_user_id(1, mock_db)
        assert result == 0


def _make_fasting_mock(record_id=1, user_id=1, **kwargs):
    """Create a HealthFasting mock with all required schema attributes set."""
    mock = MagicMock(spec=health_fasting_models.HealthFasting)
    mock.id = record_id
    mock.user_id = user_id
    mock.fast_start_time = kwargs.get("fast_start_time", datetime(2024, 1, 15, 8, 0, 0))
    mock.fast_end_time = kwargs.get("fast_end_time")
    mock.target_duration_seconds = kwargs.get("target_duration_seconds")
    mock.actual_duration_seconds = kwargs.get("actual_duration_seconds")
    mock.fasting_type = kwargs.get("fasting_type")
    mock.status = kwargs.get("status")
    mock.notes = kwargs.get("notes")
    mock.source = kwargs.get("source")
    return mock


class TestGetHealthFastingByID:
    def test_found(self, mock_db):
        mock_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_fasting
        result = health_fasting_crud.get_health_fasting_by_id_and_user_id(1, 1, mock_db)
        assert result.id == 1

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = health_fasting_crud.get_health_fasting_by_id_and_user_id(999, 1, mock_db)
        assert result is None


class TestGetHealthFastingByUserID:
    def test_with_pagination(self, mock_db):
        mock_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_fasting]
        result = health_fasting_crud.get_health_fasting_by_user_id(1, mock_db, page_number=1, num_records=10)
        assert len(result) == 1

    def test_no_pagination(self, mock_db):
        mock_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_fasting]
        result = health_fasting_crud.get_health_fasting_by_user_id(1, mock_db)
        assert len(result) == 1


class TestGetActiveFasting:
    def test_has_active(self, mock_db):
        mock_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_fasting
        result = health_fasting_crud.get_active_fasting_by_user_id(1, mock_db)
        assert result.id == 1

    def test_no_active(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = health_fasting_crud.get_active_fasting_by_user_id(1, mock_db)
        assert result is None


class TestGetCompletedFastingCount:
    def test_success(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 10
        result = health_fasting_crud.get_completed_fasting_count(1, mock_db)
        assert result == 10


class TestGetTotalFastingSeconds:
    def test_success(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 86400
        result = health_fasting_crud.get_total_fasting_seconds(1, mock_db)
        assert result == 86400


class TestGetAvgFastingDuration:
    def test_with_data(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 36000
        result = health_fasting_crud.get_avg_fasting_duration(1, mock_db)
        assert result == 36000

    def test_no_data(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = None
        result = health_fasting_crud.get_avg_fasting_duration(1, mock_db)
        assert result is None


class TestCreateHealthFasting:
    def test_success(self, mock_db):
        fasting_data = health_fasting_schema.HealthFastingCreate(
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        mock_db_fasting = _make_fasting_mock()

        with patch.object(health_fasting_models, "HealthFasting", return_value=mock_db_fasting):
            result = health_fasting_crud.create_health_fasting(1, fasting_data, mock_db)
            assert result.id == 1
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_integrity_error(self, mock_db):
        fasting_data = health_fasting_schema.HealthFastingCreate(
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        with patch.object(health_fasting_models, "HealthFasting", side_effect=IntegrityError("dup", None, None)):
            with pytest.raises(HTTPException) as e:
                health_fasting_crud.create_health_fasting(1, fasting_data, mock_db)
            assert e.value.status_code == 409


class TestEditHealthFasting:
    def test_success(self, mock_db):
        update_data = health_fasting_schema.HealthFastingUpdate(
            id=1,
            user_id=1,
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        mock_db_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_fasting
        result = health_fasting_crud.edit_health_fasting(1, update_data, mock_db)
        assert result is not None
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        update_data = health_fasting_schema.HealthFastingUpdate(
            id=999,
            user_id=1,
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_fasting_crud.edit_health_fasting(1, update_data, mock_db)
        assert e.value.status_code == 404

    def test_wrong_user(self, mock_db):
        update_data = health_fasting_schema.HealthFastingUpdate(
            id=1,
            user_id=2,
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        with pytest.raises(HTTPException) as e:
            health_fasting_crud.edit_health_fasting(1, update_data, mock_db)
        assert e.value.status_code == 403


class TestCompleteHealthFasting:
    def test_success(self, mock_db):
        complete_data = health_fasting_schema.HealthFastingComplete(
            fast_end_time=datetime(2024, 1, 15, 16, 0, 0),
        )
        mock_db_fasting = _make_fasting_mock(
            status="in_progress",
            fast_start_time=datetime(2024, 1, 15, 8, 0, 0),
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_fasting
        result = health_fasting_crud.complete_health_fasting(1, 1, complete_data, mock_db)
        assert result is not None
        mock_db.commit.assert_called_once()

    def test_not_in_progress(self, mock_db):
        complete_data = health_fasting_schema.HealthFastingComplete(
            fast_end_time=datetime(2024, 1, 15, 16, 0, 0),
        )
        mock_db_fasting = _make_fasting_mock(status="completed")
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_fasting
        with pytest.raises(HTTPException) as e:
            health_fasting_crud.complete_health_fasting(1, 1, complete_data, mock_db)
        assert e.value.status_code == 400


class TestDeleteHealthFasting:
    def test_success(self, mock_db):
        mock_db_fasting = _make_fasting_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_fasting
        health_fasting_crud.delete_health_fasting(1, 1, mock_db)
        mock_db.delete.assert_called_once_with(mock_db_fasting)
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_fasting_crud.delete_health_fasting(1, 999, mock_db)
        assert e.value.status_code == 404


class TestGetCompletedFastingDates:
    def test_success(self, mock_db):
        dates = [date(2024, 1, 15), date(2024, 1, 16)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = dates
        result = health_fasting_crud.get_completed_fasting_dates_by_user_id(1, mock_db)
        assert result == dates

    def test_empty(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = health_fasting_crud.get_completed_fasting_dates_by_user_id(1, mock_db)
        assert result == []
