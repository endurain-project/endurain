import pytest
from datetime import datetime, date as datetime_date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_sleep.crud as health_sleep_crud
import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.models as health_sleep_models


class TestGetHealthSleepNumber:
    """
    Test suite for get_health_sleep_number function.
    """

    def test_get_health_sleep_number_success(self, mock_db):
        """
        Test successful count of health sleep records for a user.
        """
        # Arrange
        user_id = 1
        expected_count = 5
        mock_db.execute.return_value.scalar_one.return_value = expected_count

        # Act
        result = health_sleep_crud.get_health_sleep_number(user_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.execute.assert_called_once()

    def test_get_health_sleep_number_zero(self, mock_db):
        """
        Test count when user has no health sleep records.
        """
        # Arrange
        user_id = 1
        mock_db.execute.return_value.scalar_one.return_value = 0

        # Act
        result = health_sleep_crud.get_health_sleep_number(user_id, mock_db)

        # Assert
        assert result == 0

    def test_get_health_sleep_number_exception(self, mock_db):
        """
        Test exception handling in get_health_sleep_number.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.get_health_sleep_number(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetAllHealthSleepByUserId:
    """
    Test suite for get_all_health_sleep_by_user_id function.
    """

    def test_get_all_health_sleep_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of all health sleep records for user.
        """
        # Arrange
        user_id = 1
        mock_sleep1 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_sleep2 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_sleep1,
            mock_sleep2,
        ]

        # Act
        result = health_sleep_crud.get_all_health_sleep_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_sleep1, mock_sleep2]
        mock_db.execute.assert_called_once()

    def test_get_all_health_sleep_by_user_id_empty(self, mock_db):
        """
        Test retrieval when user has no health sleep records.
        """
        # Arrange
        user_id = 1
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Act
        result = health_sleep_crud.get_all_health_sleep_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_all_health_sleep_by_user_id_exception(self, mock_db):
        """
        Test exception handling in get_all_health_sleep_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.get_all_health_sleep_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetHealthSleepWithPagination:
    """
    Test suite for get_health_sleep_with_pagination function.
    """

    def test_get_health_sleep_with_pagination_success(self, mock_db):
        """
        Test successful retrieval of paginated health sleep records.
        """
        # Arrange
        user_id = 1
        page_number = 2
        num_records = 5
        mock_sleep1 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_sleep2 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_sleep1,
            mock_sleep2,
        ]

        # Act
        result = health_sleep_crud.get_health_sleep_with_pagination(
            user_id, mock_db, page_number, num_records
        )

        # Assert
        assert result == [mock_sleep1, mock_sleep2]
        mock_db.execute.assert_called_once()

    def test_get_health_sleep_with_pagination_defaults(self, mock_db):
        """
        Test pagination with default values.
        """
        # Arrange
        user_id = 1
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Act
        result = health_sleep_crud.get_health_sleep_with_pagination(user_id, mock_db)

        # Assert
        mock_db.execute.assert_called_once()

    def test_get_health_sleep_with_pagination_exception(self, mock_db):
        """
        Test exception handling in get_health_sleep_with_pagination.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.get_health_sleep_with_pagination(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetHealthSleepByDate:
    """
    Test suite for get_health_sleep_by_date function.
    """

    def test_get_health_sleep_by_date_success(self, mock_db):
        """
        Test successful retrieval of health sleep by date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_sleep

        # Act
        result = health_sleep_crud.get_health_sleep_by_date(user_id, test_date, mock_db)

        # Assert
        assert result == mock_sleep
        mock_db.execute.assert_called_once()

    def test_get_health_sleep_by_date_not_found(self, mock_db):
        """
        Test retrieval when no record exists for date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = health_sleep_crud.get_health_sleep_by_date(user_id, test_date, mock_db)

        # Assert
        assert result is None

    def test_get_health_sleep_by_date_exception(self, mock_db):
        """
        Test exception handling in get_health_sleep_by_date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.get_health_sleep_by_date(user_id, test_date, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateHealthSleep:
    """
    Test suite for create_health_sleep function.
    """

    def test_create_health_sleep_success(self, mock_db):
        """
        Test successful creation of health sleep entry.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepCreate(
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
            sleep_score_overall=85,
        )

        mock_db_sleep = MagicMock()
        mock_db_sleep.id = 1
        mock_db_sleep.total_sleep_seconds = 28800
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_sleep_models,
            "HealthSleep",
            return_value=mock_db_sleep,
        ):
            # Act
            result = health_sleep_crud.create_health_sleep(
                user_id, health_sleep, mock_db
            )

            # Assert
            assert result.id == 1
            assert result.total_sleep_seconds == 28800
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_health_sleep_with_none_date(self, mock_db):
        """
        Test creation with None date sets current date via schema validator.
        """
        # Arrange
        user_id = 1
        # Schema validator sets date to today when not provided
        health_sleep = health_sleep_schema.HealthSleepCreate(total_sleep_seconds=28800)

        mock_db_sleep = MagicMock()
        mock_db_sleep.id = 1
        mock_db_sleep.date = health_sleep.date  # Will be today's date from validator
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_sleep_models,
            "HealthSleep",
            return_value=mock_db_sleep,
        ):
            # Act
            result = health_sleep_crud.create_health_sleep(
                user_id, health_sleep, mock_db
            )

            # Assert
            assert result.id == 1
            # Schema validator should have set today's date
            assert health_sleep.date == datetime_date.today()

    def test_create_health_sleep_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepCreate(
            date=datetime_date(2024, 1, 15), total_sleep_seconds=28800
        )

        mock_db_sleep = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            health_sleep_models,
            "HealthSleep",
            return_value=mock_db_sleep,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_sleep_crud.create_health_sleep(user_id, health_sleep, mock_db)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Duplicate entry error" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_health_sleep_exception(self, mock_db):
        """
        Test exception handling in create_health_sleep.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepCreate(
            date=datetime_date(2024, 1, 15), total_sleep_seconds=28800
        )

        mock_db.add.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.create_health_sleep(user_id, health_sleep, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestEditHealthSleep:
    """
    Test suite for edit_health_sleep function.
    """

    def test_edit_health_sleep_success(self, mock_db):
        """
        Test successful edit of health sleep entry.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepUpdate(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=32400,
            sleep_score_overall=90,
        )

        mock_db_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db_sleep.total_sleep_seconds = 32400
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_sleep

        # Act
        result = health_sleep_crud.edit_health_sleep(user_id, health_sleep, mock_db)

        # Assert
        assert result.total_sleep_seconds == 32400
        mock_db.commit.assert_called_once()

    def test_edit_health_sleep_not_found(self, mock_db):
        """
        Test edit when health sleep record not found.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepUpdate(
            id=999,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=32400,
        )

        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.edit_health_sleep(user_id, health_sleep, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Health sleep not found"

    def test_edit_health_sleep_exception(self, mock_db):
        """
        Test exception handling in edit_health_sleep.
        """
        # Arrange
        user_id = 1
        health_sleep = health_sleep_schema.HealthSleepUpdate(
            id=1, user_id=1, total_sleep_seconds=32400
        )

        # Mock get_health_sleep_by_id_and_user_id to return a record
        mock_db_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_sleep
        # Then make commit raise SQLAlchemyError
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.edit_health_sleep(user_id, health_sleep, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestDeleteHealthSleep:
    """
    Test suite for delete_health_sleep function.
    """

    def test_delete_health_sleep_success(self, mock_db):
        """
        Test successful deletion of health sleep entry.
        """
        # Arrange
        user_id = 1
        health_sleep_id = 1

        # Mock get_health_sleep_by_id_and_user_id to return a record
        mock_db_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_sleep

        # Act
        health_sleep_crud.delete_health_sleep(user_id, health_sleep_id, mock_db)

        # Assert
        mock_db.delete.assert_called_once_with(mock_db_sleep)
        mock_db.commit.assert_called_once()

    def test_delete_health_sleep_not_found(self, mock_db):
        """
        Test deletion when health sleep record not found.
        """
        # Arrange
        user_id = 1
        health_sleep_id = 999

        # Mock get_health_sleep_by_id_and_user_id to return None
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.delete_health_sleep(user_id, health_sleep_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert f"Health sleep with id {health_sleep_id}" in exc_info.value.detail

    def test_delete_health_sleep_exception(self, mock_db):
        """
        Test exception handling in delete_health_sleep.
        """
        # Arrange
        user_id = 1
        health_sleep_id = 1

        # Mock get_health_sleep_by_id_and_user_id to return a record
        mock_db_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_db_sleep
        # Then make delete raise SQLAlchemyError
        mock_db.delete.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_sleep_crud.delete_health_sleep(user_id, health_sleep_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()
