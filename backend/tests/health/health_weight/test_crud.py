import pytest
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import health.health_weight.crud as health_weight_crud
import health.health_weight.schema as health_weight_schema
import health.health_weight.models as health_weight_models


class TestGetAllHealthWeight:
    """
    Test suite for get_all_health_weight function.
    """

    def test_get_all_health_weight_success(self, mock_db):
        """
        Test successful retrieval of all health weight records.
        """
        # Arrange
        mock_weight1 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_all_health_weight(mock_db)

        # Assert
        assert result == [mock_weight1, mock_weight2]
        mock_db.execute.assert_called_once()

    def test_get_all_health_weight_exception(self, mock_db):
        """
        Test exception handling in get_all_health_weight.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_all_health_weight(mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthWeightNumber:
    """
    Test suite for get_health_weight_number function.
    """

    def test_get_health_weight_number_success(self, mock_db):
        """
        Test successful count of health weight records for a user.
        """
        # Arrange
        user_id = 1
        expected_count = 5
        mock_db.execute.return_value.scalar_one.return_value = expected_count

        # Act
        result = health_weight_crud.get_health_weight_number(user_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.execute.assert_called_once()

    def test_get_health_weight_number_none_returns_zero(self, mock_db):
        """
        Test count when result is zero.
        """
        # Arrange
        user_id = 1
        mock_db.execute.return_value.scalar_one.return_value = 0

        # Act
        result = health_weight_crud.get_health_weight_number(user_id, mock_db)

        # Assert
        assert result == 0

    def test_get_health_weight_number_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_number.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_number(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetAllHealthWeightByUserId:
    """
    Test suite for get_all_health_weight_by_user_id function.
    """

    def test_get_all_health_weight_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of all health weight records for user.
        """
        # Arrange
        user_id = 1
        mock_weight1 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_all_health_weight_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_weight1, mock_weight2]
        mock_db.execute.assert_called_once()

    def test_get_all_health_weight_by_user_id_empty(self, mock_db):
        """
        Test retrieval when user has no records.
        """
        # Arrange
        user_id = 1
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_all_health_weight_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_all_health_weight_by_user_id_exception(self, mock_db):
        """
        Test exception handling in get_all_health_weight_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_all_health_weight_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthWeightWithPagination:
    """
    Test suite for get_health_weight_with_pagination function.
    """

    def test_get_health_weight_with_pagination_success(self, mock_db):
        """
        Test successful retrieval of paginated health weight records.
        """
        # Arrange
        user_id = 1
        page_number = 2
        num_records = 5
        mock_weight1 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_health_weight_with_pagination(
            user_id, mock_db, page_number, num_records
        )

        # Assert
        assert result == [mock_weight1, mock_weight2]
        mock_db.execute.assert_called_once()

    def test_get_health_weight_with_pagination_defaults(self, mock_db):
        """
        Test pagination with default values.
        """
        # Arrange
        user_id = 1
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_health_weight_with_pagination(user_id, mock_db)

        # Assert
        assert result == []
        mock_db.execute.assert_called_once()

    def test_get_health_weight_with_pagination_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_with_pagination.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_with_pagination(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthWeightByDate:
    """
    Test suite for get_health_weight_by_date function.
    """

    def test_get_health_weight_by_date_success(self, mock_db):
        """
        Test successful retrieval of health weight by date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_weight = MagicMock(spec=health_weight_models.HealthWeight)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_weight

        # Act
        result = health_weight_crud.get_health_weight_by_date(
            user_id, test_date, mock_db
        )

        # Assert
        assert result == mock_weight
        mock_db.execute.assert_called_once()

    def test_get_health_weight_by_date_not_found(self, mock_db):
        """
        Test retrieval when no record exists for date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = health_weight_crud.get_health_weight_by_date(
            user_id, test_date, mock_db
        )

        # Assert
        assert result is None

    def test_get_health_weight_by_date_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_by_date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_by_date(user_id, test_date, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateHealthWeight:
    """
    Test suite for create_health_weight function.
    """

    @patch("health.health_weight.crud.health_weight_utils.calculate_bmi")
    def test_create_health_weight_success(self, mock_calculate_bmi, mock_db):
        """
        Test successful creation of health weight entry.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=None,
        )
        updated_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=24.5,
        )
        mock_calculate_bmi.return_value = updated_weight

        mock_db_weight = MagicMock()
        mock_db_weight.id = 1
        mock_db_weight.bmi = 24.5
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_weight_models,
            "HealthWeight",
            return_value=mock_db_weight,
        ):
            # Act
            result = health_weight_crud.create_health_weight(
                user_id, health_weight, mock_db
            )

            # Assert
            assert result.id == 1
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_health_weight_with_bmi_provided(self, mock_db):
        """
        Test creation with BMI already provided skips calculation.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=24.5,
        )

        mock_db_weight = MagicMock()
        mock_db_weight.id = 1
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_weight_models,
            "HealthWeight",
            return_value=mock_db_weight,
        ):
            # Act
            result = health_weight_crud.create_health_weight(
                user_id, health_weight, mock_db
            )

            # Assert
            assert result.id == 1
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_create_health_weight_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=75.5, bmi=24.5
        )

        mock_db_weight = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            health_weight_models,
            "HealthWeight",
            return_value=mock_db_weight,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_weight_crud.create_health_weight(user_id, health_weight, mock_db)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Duplicate entry error" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_health_weight_exception(self, mock_db):
        """
        Test exception handling in create_health_weight.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=75.5, bmi=24.5
        )

        mock_db.add.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.create_health_weight(user_id, health_weight, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()


class TestEditHealthWeight:
    """
    Test suite for edit_health_weight function.
    """

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    @patch("health.health_weight.crud.health_weight_utils.calculate_bmi")
    def test_edit_health_weight_success(
        self, mock_calculate_bmi, mock_get_by_id, mock_db
    ):
        """
        Test successful edit of health weight entry.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=None,
        )
        updated_weight = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=24.7,
        )
        mock_calculate_bmi.return_value = updated_weight

        mock_db_weight = MagicMock(spec=health_weight_models.HealthWeight)
        mock_get_by_id.return_value = mock_db_weight

        # Act
        result = health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_edit_health_weight_not_found(self, mock_get_by_id, mock_db):
        """
        Test edit when health weight record not found.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(
            id=999,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
        )
        mock_get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Health weight not found"

    def test_edit_health_weight_forbidden_different_user(self, mock_db):
        """
        Test edit forbidden when user_id doesn't match.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=2,  # Different user
            date=datetime_date(2024, 1, 15),
            weight=76.0,
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_edit_health_weight_with_bmi_provided(self, mock_get_by_id, mock_db):
        """
        Test edit without BMI calculation when BMI provided.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=25.0,
        )

        mock_db_weight = MagicMock(spec=health_weight_models.HealthWeight)
        mock_get_by_id.return_value = mock_db_weight

        # Act
        result = health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        # Assert
        mock_db.commit.assert_called_once()

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_edit_health_weight_exception(self, mock_get_by_id, mock_db):
        """
        Test exception handling in edit_health_weight.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(
            id=1, user_id=1, weight=76.0
        )

        mock_get_by_id.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()


class TestDeleteHealthWeight:
    """
    Test suite for delete_health_weight function.
    """

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_delete_health_weight_success(self, mock_get_by_id, mock_db):
        """
        Test successful deletion of health weight entry.
        """
        # Arrange
        user_id = 1
        health_weight_id = 1

        mock_db_weight = MagicMock(spec=health_weight_models.HealthWeight)
        mock_get_by_id.return_value = mock_db_weight

        # Act
        health_weight_crud.delete_health_weight(user_id, health_weight_id, mock_db)

        # Assert
        mock_db.delete.assert_called_once_with(mock_db_weight)
        mock_db.commit.assert_called_once()

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_delete_health_weight_not_found(self, mock_get_by_id, mock_db):
        """
        Test deletion when health weight record not found.
        """
        # Arrange
        user_id = 1
        health_weight_id = 999
        mock_get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.delete_health_weight(user_id, health_weight_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert f"Health weight with id {health_weight_id}" in exc_info.value.detail

    @patch("health.health_weight.crud.get_health_weight_by_id_and_user_id")
    def test_delete_health_weight_exception(self, mock_get_by_id, mock_db):
        """
        Test exception handling in delete_health_weight.
        """
        # Arrange
        user_id = 1
        health_weight_id = 1
        mock_get_by_id.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.delete_health_weight(user_id, health_weight_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()
