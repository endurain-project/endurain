from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema


def _make_poop_mock(record_id=1, user_id=1, **kwargs):
    """Create a HealthPoop mock with all required schema attributes set."""
    mock = MagicMock(spec=health_poop_models.HealthPoop)
    mock.id = record_id
    mock.user_id = user_id
    mock.date_time = kwargs.get("date_time", datetime(2024, 1, 15, 10, 0, 0))
    mock.bristol_type = kwargs.get("bristol_type")
    mock.color = kwargs.get("color")
    mock.notes = kwargs.get("notes")
    mock.source = kwargs.get("source")
    return mock


class TestGetHealthPoopNumber:
    def test_success(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3
        result = health_poop_crud.get_health_poop_number_by_user_id(1, mock_db)
        assert result == 3


class TestGetHealthPoopByID:
    def test_found(self, mock_db):
        mock_poop = _make_poop_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_poop
        result = health_poop_crud.get_health_poop_by_id_and_user_id(1, 1, mock_db)
        assert result.id == 1

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = health_poop_crud.get_health_poop_by_id_and_user_id(999, 1, mock_db)
        assert result is None


class TestGetHealthPoopByUserID:
    def test_with_pagination(self, mock_db):
        mock_poop = _make_poop_mock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_poop]
        result = health_poop_crud.get_health_poop_by_user_id(1, mock_db, page_number=1, num_records=10)
        assert len(result) == 1

    def test_no_pagination(self, mock_db):
        mock_poop = _make_poop_mock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_poop]
        result = health_poop_crud.get_health_poop_by_user_id(1, mock_db)
        assert len(result) == 1


class TestGetHealthPoopByDate:
    def test_success(self, mock_db):
        mock_poop = _make_poop_mock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_poop]
        result = health_poop_crud.get_health_poop_by_date_and_user_id(1, "2024-01-15", mock_db)
        assert len(result) == 1

    def test_empty(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = health_poop_crud.get_health_poop_by_date_and_user_id(1, "2024-01-15", mock_db)
        assert result == []


class TestCreateHealthPoop:
    def test_success(self, mock_db):
        poop_data = health_poop_schema.HealthPoopCreate(
            date_time=datetime(2024, 1, 15, 10, 0, 0),
        )
        mock_db_poop = _make_poop_mock()

        with patch.object(health_poop_models, "HealthPoop", return_value=mock_db_poop):
            result = health_poop_crud.create_health_poop(1, poop_data, mock_db)
            assert result.id == 1
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_integrity_error(self, mock_db):
        poop_data = health_poop_schema.HealthPoopCreate(
            date_time=datetime(2024, 1, 15, 10, 0, 0),
        )
        with patch.object(health_poop_models, "HealthPoop", side_effect=IntegrityError("dup", None, None)):
            with pytest.raises(HTTPException) as e:
                health_poop_crud.create_health_poop(1, poop_data, mock_db)
            assert e.value.status_code == 409


class TestEditHealthPoop:
    def test_success(self, mock_db):
        update_data = health_poop_schema.HealthPoopUpdate(
            id=1,
            user_id=1,
            date_time=datetime(2024, 1, 15, 10, 0, 0),
        )
        mock_db_poop = _make_poop_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_poop
        result = health_poop_crud.edit_health_poop(1, update_data, mock_db)
        assert result is not None
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        update_data = health_poop_schema.HealthPoopUpdate(
            id=999,
            user_id=1,
            date_time=datetime(2024, 1, 15, 10, 0, 0),
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_poop_crud.edit_health_poop(1, update_data, mock_db)
        assert e.value.status_code == 404

    def test_wrong_user(self, mock_db):
        update_data = health_poop_schema.HealthPoopUpdate(
            id=1,
            user_id=2,
            date_time=datetime(2024, 1, 15, 10, 0, 0),
        )
        with pytest.raises(HTTPException) as e:
            health_poop_crud.edit_health_poop(1, update_data, mock_db)
        assert e.value.status_code == 403


class TestDeleteHealthPoop:
    def test_success(self, mock_db):
        mock_db_poop = _make_poop_mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_poop
        health_poop_crud.delete_health_poop(1, 1, mock_db)
        mock_db.delete.assert_called_once_with(mock_db_poop)
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_poop_crud.delete_health_poop(1, 999, mock_db)
        assert e.value.status_code == 404
