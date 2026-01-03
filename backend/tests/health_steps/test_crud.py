import pytest
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

import health.health_steps.crud as health_steps_crud
import health.health_steps.schema as health_steps_schema
import health.health_steps.models as health_steps_models


class TestGetHealthStepsNumber:
    """
    Test suite for get_health_steps_number function.
    """

    def test_get_health_steps_number_success(self, mock_db):
        """
        Test successful count of health steps records for a user.
        """
        # Arrange
        user_id = 1
        expected_count = 5
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.count.return_value = expected_count

        # Act
        result = health_steps_crud.get_health_steps_number(user_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.query.assert_called_once_with(health_steps_models.HealthSteps)

    def test_get_health_steps_number_zero(self, mock_db):
        """
        Test count when user has no health steps records.
        """
        # Arrange
        user_id = 1
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.count.return_value = 0

        # Act
        result = health_steps_crud.get_health_steps_number(user_id, mock_db)

        # Assert
        assert result == 0

    def test_get_health_steps_number_exception(self, mock_db):
        """
        Test exception handling in get_health_steps_number.
        """
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.get_health_steps_number(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Internal Server Error"


class TestGetAllHealthStepsByUserId:
    """
    Test suite for get_all_health_steps_by_user_id function.
    """

    def test_get_all_health_steps_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of all health steps records for user.
        """
        # Arrange
        user_id = 1
        mock_steps1 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_steps2 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.order_by.return_value.all.return_value = [
            mock_steps1,
            mock_steps2,
        ]

        # Act
        result = health_steps_crud.get_all_health_steps_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_steps1, mock_steps2]
        mock_db.query.assert_called_once_with(health_steps_models.HealthSteps)

    def test_get_all_health_steps_by_user_id_empty(self, mock_db):
        """
        Test retrieval when user has no health steps records.
        """
        # Arrange
        user_id = 1
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.order_by.return_value.all.return_value = []

        # Act
        result = health_steps_crud.get_all_health_steps_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_all_health_steps_by_user_id_exception(self, mock_db):
        """
        Test exception handling in get_all_health_steps_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.get_all_health_steps_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetHealthStepsWithPagination:
    """
    Test suite for get_health_steps_with_pagination function.
    """

    def test_get_health_steps_with_pagination_success(self, mock_db):
        """
        Test successful retrieval of paginated health steps records.
        """
        # Arrange
        user_id = 1
        page_number = 2
        num_records = 5
        mock_steps1 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_steps2 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_offset = mock_order.offset.return_value
        mock_offset.limit.return_value.all.return_value = [
            mock_steps1,
            mock_steps2,
        ]

        # Act
        result = health_steps_crud.get_health_steps_with_pagination(
            user_id, mock_db, page_number, num_records
        )

        # Assert
        assert result == [mock_steps1, mock_steps2]
        mock_order.offset.assert_called_once_with(5)
        mock_offset.limit.assert_called_once_with(5)

    def test_get_health_steps_with_pagination_defaults(self, mock_db):
        """
        Test pagination with default values.
        """
        # Arrange
        user_id = 1
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_offset = mock_order.offset.return_value
        mock_offset.limit.return_value.all.return_value = []

        # Act
        result = health_steps_crud.get_health_steps_with_pagination(user_id, mock_db)

        # Assert
        mock_order.offset.assert_called_once_with(0)
        mock_offset.limit.assert_called_once_with(5)

    def test_get_health_steps_with_pagination_exception(self, mock_db):
        """
        Test exception handling in get_health_steps_with_pagination.
        """
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.get_health_steps_with_pagination(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetHealthStepsByDate:
    """
    Test suite for get_health_steps_by_date function.
    """

    def test_get_health_steps_by_date_success(self, mock_db):
        """
        Test successful retrieval of health steps by date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_steps = MagicMock(spec=health_steps_models.HealthSteps)
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.return_value = mock_steps

        # Act
        result = health_steps_crud.get_health_steps_by_date(user_id, test_date, mock_db)

        # Assert
        assert result == mock_steps
        mock_db.query.assert_called_once_with(health_steps_models.HealthSteps)

    def test_get_health_steps_by_date_not_found(self, mock_db):
        """
        Test retrieval when no record exists for date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.return_value = None

        # Act
        result = health_steps_crud.get_health_steps_by_date(user_id, test_date, mock_db)

        # Assert
        assert result is None

    def test_get_health_steps_by_date_exception(self, mock_db):
        """
        Test exception handling in get_health_steps_by_date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.get_health_steps_by_date(user_id, test_date, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateHealthSteps:
    """
    Test suite for create_health_steps function.
    """

    def test_create_health_steps_success(self, mock_db):
        """
        Test successful creation of health steps entry.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            date=datetime_date(2024, 1, 15),
            steps=10000,
            source="garmin",
        )

        mock_db_steps = MagicMock()
        mock_db_steps.id = 1
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_steps_models,
            "HealthSteps",
            return_value=mock_db_steps,
        ):
            # Act
            result = health_steps_crud.create_health_steps(
                user_id, health_steps, mock_db
            )

            # Assert
            assert result.id == 1
            assert result.steps == 10000
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    @patch("health.health_steps.crud.func")
    def test_create_health_steps_with_none_date(self, mock_func, mock_db):
        """
        Test creation with None date sets current date.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            date=None, steps=10000, source="garmin"
        )

        # Mock func.now() to return a proper date object
        mock_func.now.return_value = datetime_date(2024, 1, 15)

        mock_db_steps = MagicMock()
        mock_db_steps.id = 1
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_steps_models,
            "HealthSteps",
            return_value=mock_db_steps,
        ):
            # Act
            result = health_steps_crud.create_health_steps(
                user_id, health_steps, mock_db
            )

            # Assert
            mock_func.now.assert_called_once()
            assert result.id == 1
            assert result.date == datetime_date(2024, 1, 15)

    def test_create_health_steps_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            date=datetime_date(2024, 1, 15), steps=10000, source="garmin"
        )

        mock_db_steps = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            health_steps_models,
            "HealthSteps",
            return_value=mock_db_steps,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_steps_crud.create_health_steps(user_id, health_steps, mock_db)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Duplicate entry error" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_health_steps_exception(self, mock_db):
        """
        Test exception handling in create_health_steps.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            date=datetime_date(2024, 1, 15), steps=10000
        )

        mock_db.add.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.create_health_steps(user_id, health_steps, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestEditHealthSteps:
    """
    Test suite for edit_health_steps function.
    """

    def test_edit_health_steps_success(self, mock_db):
        """
        Test successful edit of health steps entry.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            id=1, date=datetime_date(2024, 1, 15), steps=12000
        )

        mock_db_steps = MagicMock(spec=health_steps_models.HealthSteps)
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.return_value = mock_db_steps

        # Act
        result = health_steps_crud.edit_health_steps(user_id, health_steps, mock_db)

        # Assert
        assert result.steps == 12000
        mock_db.commit.assert_called_once()

    def test_edit_health_steps_not_found(self, mock_db):
        """
        Test edit when health steps record not found.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            id=999, date=datetime_date(2024, 1, 15), steps=12000
        )

        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.edit_health_steps(user_id, health_steps, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Health steps not found"

    def test_edit_health_steps_update_multiple_fields(self, mock_db):
        """
        Test edit updates multiple fields correctly.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(
            id=1,
            date=datetime_date(2024, 1, 15),
            steps=15000,
            source="garmin",
        )

        mock_db_steps = MagicMock(spec=health_steps_models.HealthSteps)
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.return_value = mock_db_steps

        # Act
        result = health_steps_crud.edit_health_steps(user_id, health_steps, mock_db)

        # Assert
        mock_db.commit.assert_called_once()

    def test_edit_health_steps_exception(self, mock_db):
        """
        Test exception handling in edit_health_steps.
        """
        # Arrange
        user_id = 1
        health_steps = health_steps_schema.HealthSteps(id=1, steps=12000)

        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.edit_health_steps(user_id, health_steps, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestDeleteHealthSteps:
    """
    Test suite for delete_health_steps function.
    """

    def test_delete_health_steps_success(self, mock_db):
        """
        Test successful deletion of health steps entry.
        """
        # Arrange
        user_id = 1
        health_steps_id = 1

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = 1

        # Act
        health_steps_crud.delete_health_steps(user_id, health_steps_id, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.query.assert_called_once_with(health_steps_models.HealthSteps)

    def test_delete_health_steps_not_found(self, mock_db):
        """
        Test deletion when health steps record not found.
        """
        # Arrange
        user_id = 1
        health_steps_id = 999

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = 0

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.delete_health_steps(user_id, health_steps_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert f"Health steps with id {health_steps_id}" in exc_info.value.detail

    def test_delete_health_steps_exception(self, mock_db):
        """
        Test exception handling in delete_health_steps.
        """
        # Arrange
        user_id = 1
        health_steps_id = 1

        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_steps_crud.delete_health_steps(user_id, health_steps_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()
