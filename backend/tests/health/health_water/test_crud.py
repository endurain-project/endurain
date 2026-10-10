from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema


class TestGetHealthWaterNumber:
    def test_success(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 5
        result = health_water_crud.get_health_water_number_by_user_id(1, mock_db)
        assert result == 5


class TestGetHealthWaterByID:
    def test_found(self, mock_db):
        mock_water = MagicMock(spec=health_water_models.HealthWater)
        mock_water.id = 1
        mock_water.user_id = 1
        mock_water.date = None
        mock_water.amount_ml = None
        mock_water.source = None
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_water
        result = health_water_crud.get_health_water_by_id_and_user_id(1, 1, mock_db)
        assert result.id == 1

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = health_water_crud.get_health_water_by_id_and_user_id(999, 1, mock_db)
        assert result is None


class TestGetHealthWaterByUserID:
    def test_with_pagination(self, mock_db):
        mock_water = MagicMock(spec=health_water_models.HealthWater)
        mock_water.id = 1
        mock_water.user_id = 1
        mock_water.date = None
        mock_water.amount_ml = None
        mock_water.source = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_water]
        result = health_water_crud.get_health_water_by_user_id(1, mock_db, page_number=1, num_records=10)
        assert len(result) == 1

    def test_no_pagination(self, mock_db):
        mock_water = MagicMock(spec=health_water_models.HealthWater)
        mock_water.id = 1
        mock_water.user_id = 1
        mock_water.date = None
        mock_water.amount_ml = None
        mock_water.source = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_water]
        result = health_water_crud.get_health_water_by_user_id(1, mock_db)
        assert len(result) == 1


class TestGetHealthWaterByDate:
    def test_found(self, mock_db):
        mock_water = MagicMock(spec=health_water_models.HealthWater)
        mock_water.id = 1
        mock_water.user_id = 1
        mock_water.date = None
        mock_water.amount_ml = None
        mock_water.source = None
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_water
        result = health_water_crud.get_health_water_by_date_and_user_id(1, "2024-01-15", mock_db)
        assert result.id == 1

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = health_water_crud.get_health_water_by_date_and_user_id(1, "2024-01-15", mock_db)
        assert result is None


class TestCreateHealthWater:
    def test_success(self, mock_db):
        water_data = health_water_schema.HealthWaterCreate(amount_ml=500.0)
        mock_db_water = MagicMock(spec=health_water_models.HealthWater)
        mock_db_water.id = 1
        mock_db_water.user_id = 1
        mock_db_water.date = None
        mock_db_water.amount_ml = None
        mock_db_water.source = None

        with patch.object(health_water_models, "HealthWater", return_value=mock_db_water):
            result = health_water_crud.create_health_water(1, water_data, mock_db)
            assert result.id == 1
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_integrity_error(self, mock_db):
        water_data = health_water_schema.HealthWaterCreate(amount_ml=500.0)
        with patch.object(health_water_models, "HealthWater", side_effect=IntegrityError("dup", None, None)):
            with pytest.raises(HTTPException) as e:
                health_water_crud.create_health_water(1, water_data, mock_db)
            assert e.value.status_code == 409


class TestEditHealthWater:
    def test_success(self, mock_db):
        from datetime import date

        update_data = health_water_schema.HealthWaterUpdate(
            id=1,
            user_id=1,
            date=date(2024, 1, 15),
        )
        mock_db_water = MagicMock(spec=health_water_models.HealthWater)
        mock_db_water.amount_ml = None
        mock_db_water.source = None

        with patch.object(
            health_water_crud, "_get_health_water_model_by_id_and_user_id_or_404", return_value=mock_db_water
        ):
            result = health_water_crud.edit_health_water(1, update_data, mock_db)
            assert result is not None
            mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        from datetime import date

        update_data = health_water_schema.HealthWaterUpdate(
            id=999,
            user_id=1,
            date=date(2024, 1, 15),
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_water_crud.edit_health_water(1, update_data, mock_db)
        assert e.value.status_code == 404

    def test_wrong_user(self, mock_db):
        from datetime import date

        update_data = health_water_schema.HealthWaterUpdate(
            id=1,
            user_id=2,
            date=date(2024, 1, 15),
        )
        with pytest.raises(HTTPException) as e:
            health_water_crud.edit_health_water(1, update_data, mock_db)
        assert e.value.status_code == 403


class TestDeleteHealthWater:
    def test_success(self, mock_db):
        mock_db_water = MagicMock(spec=health_water_models.HealthWater)
        with patch.object(
            health_water_crud, "_get_health_water_model_by_id_and_user_id_or_404", return_value=mock_db_water
        ):
            health_water_crud.delete_health_water(1, 1, mock_db)
            mock_db.delete.assert_called_once_with(mock_db_water)
            mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(HTTPException) as e:
            health_water_crud.delete_health_water(1, 999, mock_db)
        assert e.value.status_code == 404
