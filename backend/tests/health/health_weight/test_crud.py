from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema


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
        mock_weight1.id = 1
        mock_weight1.user_id = 1
        mock_weight1.date = None
        mock_weight1.weight = None
        mock_weight1.bmi = None
        mock_weight1.body_fat = None
        mock_weight1.body_water = None
        mock_weight1.bone_mass = None
        mock_weight1.muscle_mass = None
        mock_weight1.physique_rating = None
        mock_weight1.visceral_fat = None
        mock_weight1.metabolic_age = None
        mock_weight1.source = None
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2.id = 2
        mock_weight2.user_id = 1
        mock_weight2.date = None
        mock_weight2.weight = None
        mock_weight2.bmi = None
        mock_weight2.body_fat = None
        mock_weight2.body_water = None
        mock_weight2.bone_mass = None
        mock_weight2.muscle_mass = None
        mock_weight2.physique_rating = None
        mock_weight2.visceral_fat = None
        mock_weight2.metabolic_age = None
        mock_weight2.source = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_all_health_weight(mock_db)

        # Assert
        assert len(result) == 2
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
    Test suite for get_health_weight_number_by_user_id function.
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
        result = health_weight_crud.get_health_weight_number_by_user_id(user_id, mock_db)

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
        result = health_weight_crud.get_health_weight_number_by_user_id(user_id, mock_db)

        # Assert
        assert result == 0

    def test_get_health_weight_number_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_number_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_number_by_user_id(user_id, mock_db)

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
        mock_weight1.id = 1
        mock_weight1.user_id = user_id
        mock_weight1.date = None
        mock_weight1.weight = None
        mock_weight1.bmi = None
        mock_weight1.body_fat = None
        mock_weight1.body_water = None
        mock_weight1.bone_mass = None
        mock_weight1.muscle_mass = None
        mock_weight1.physique_rating = None
        mock_weight1.visceral_fat = None
        mock_weight1.metabolic_age = None
        mock_weight1.source = None
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2.id = 2
        mock_weight2.user_id = user_id
        mock_weight2.date = None
        mock_weight2.weight = None
        mock_weight2.bmi = None
        mock_weight2.body_fat = None
        mock_weight2.body_water = None
        mock_weight2.bone_mass = None
        mock_weight2.muscle_mass = None
        mock_weight2.physique_rating = None
        mock_weight2.visceral_fat = None
        mock_weight2.metabolic_age = None
        mock_weight2.source = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_all_health_weight_by_user_id(user_id, mock_db)

        # Assert
        assert len(result) == 2
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
    Test suite for get_health_weight_by_user_id function.
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
        mock_weight1.id = 1
        mock_weight1.user_id = user_id
        mock_weight1.date = None
        mock_weight1.weight = None
        mock_weight1.bmi = None
        mock_weight1.body_fat = None
        mock_weight1.body_water = None
        mock_weight1.bone_mass = None
        mock_weight1.muscle_mass = None
        mock_weight1.physique_rating = None
        mock_weight1.visceral_fat = None
        mock_weight1.metabolic_age = None
        mock_weight1.source = None
        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2.id = 2
        mock_weight2.user_id = user_id
        mock_weight2.date = None
        mock_weight2.weight = None
        mock_weight2.bmi = None
        mock_weight2.body_fat = None
        mock_weight2.body_water = None
        mock_weight2.bone_mass = None
        mock_weight2.muscle_mass = None
        mock_weight2.physique_rating = None
        mock_weight2.visceral_fat = None
        mock_weight2.metabolic_age = None
        mock_weight2.source = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_weight1, mock_weight2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_weight_crud.get_health_weight_by_user_id(user_id, mock_db, page_number, num_records)

        # Assert
        assert len(result) == 2
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
        result = health_weight_crud.get_health_weight_by_user_id(user_id, mock_db)

        # Assert
        assert result == []
        mock_db.execute.assert_called_once()

    def test_get_health_weight_with_pagination_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthWeightByDate:
    """
    Test suite for get_health_weight_by_date_and_user_id function.
    """

    def test_get_health_weight_by_date_success(self, mock_db):
        """
        Test successful retrieval of health weight by date.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_weight = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight.id = 1
        mock_weight.user_id = user_id
        mock_weight.date = None
        mock_weight.weight = None
        mock_weight.bmi = None
        mock_weight.body_fat = None
        mock_weight.body_water = None
        mock_weight.bone_mass = None
        mock_weight.muscle_mass = None
        mock_weight.physique_rating = None
        mock_weight.visceral_fat = None
        mock_weight.metabolic_age = None
        mock_weight.source = None
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_weight

        # Act
        result = health_weight_crud.get_health_weight_by_date_and_user_id(user_id, test_date, mock_db)

        # Assert
        assert result.id == 1
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
        result = health_weight_crud.get_health_weight_by_date_and_user_id(user_id, test_date, mock_db)

        # Assert
        assert result is None

    def test_get_health_weight_by_date_exception(self, mock_db):
        """
        Test exception handling in get_health_weight_by_date_and_user_id.
        """
        # Arrange
        user_id = 1
        test_date = "2024-01-15"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.get_health_weight_by_date_and_user_id(user_id, test_date, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateHealthWeight:
    """
    Test suite for create_health_weight function.
    """

    @patch("modules.health.health_weight.crud.health_weight_utils.calculate_bmi")
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
        mock_db_weight.user_id = user_id
        mock_db_weight.bmi = 24.5
        mock_db_weight.date = None
        mock_db_weight.weight = None
        mock_db_weight.body_fat = None
        mock_db_weight.body_water = None
        mock_db_weight.bone_mass = None
        mock_db_weight.muscle_mass = None
        mock_db_weight.physique_rating = None
        mock_db_weight.visceral_fat = None
        mock_db_weight.metabolic_age = None
        mock_db_weight.source = None
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_weight_models,
            "HealthWeight",
            return_value=mock_db_weight,
        ):
            # Act
            result = health_weight_crud.create_health_weight(user_id, health_weight, mock_db)

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
        mock_db_weight.user_id = user_id
        mock_db_weight.bmi = 24.5
        mock_db_weight.date = None
        mock_db_weight.weight = None
        mock_db_weight.body_fat = None
        mock_db_weight.body_water = None
        mock_db_weight.bone_mass = None
        mock_db_weight.muscle_mass = None
        mock_db_weight.physique_rating = None
        mock_db_weight.visceral_fat = None
        mock_db_weight.metabolic_age = None
        mock_db_weight.source = None
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_weight_models,
            "HealthWeight",
            return_value=mock_db_weight,
        ):
            # Act
            result = health_weight_crud.create_health_weight(user_id, health_weight, mock_db)

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
        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.5, bmi=24.5)

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
        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.5, bmi=24.5)

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

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
    @patch("modules.health.health_weight.crud.health_weight_utils.calculate_bmi")
    def test_edit_health_weight_success(self, mock_calculate_bmi, mock_get_by_id, mock_db):
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
        mock_db_weight.body_fat = None
        mock_db_weight.body_water = None
        mock_db_weight.bone_mass = None
        mock_db_weight.muscle_mass = None
        mock_db_weight.physique_rating = None
        mock_db_weight.visceral_fat = None
        mock_db_weight.metabolic_age = None
        mock_db_weight.source = None
        mock_get_by_id.return_value = mock_db_weight

        # Act
        health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
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
        mock_get_by_id.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight not found",
        )

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

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
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
        mock_db_weight.body_fat = None
        mock_db_weight.body_water = None
        mock_db_weight.bone_mass = None
        mock_db_weight.muscle_mass = None
        mock_db_weight.physique_rating = None
        mock_db_weight.visceral_fat = None
        mock_db_weight.metabolic_age = None
        mock_db_weight.source = None
        mock_get_by_id.return_value = mock_db_weight

        # Act
        health_weight_crud.edit_health_weight(user_id, health_weight, mock_db)

        # Assert
        mock_db.commit.assert_called_once()

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
    def test_edit_health_weight_exception(self, mock_get_by_id, mock_db):
        """
        Test exception handling in edit_health_weight.
        """
        # Arrange
        user_id = 1
        health_weight = health_weight_schema.HealthWeightUpdate(id=1, user_id=1, weight=76.0)

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

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
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

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
    def test_delete_health_weight_not_found(self, mock_get_by_id, mock_db):
        """
        Test deletion when health weight record not found.
        """
        # Arrange
        user_id = 1
        health_weight_id = 999
        mock_get_by_id.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight not found",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.delete_health_weight(user_id, health_weight_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Health weight not found"

    @patch("modules.health.health_weight.crud._get_health_weight_model_by_id_and_user_id_or_404")
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


class TestRecalculateBmiForUser:
    """
    Test suite for recalculate_bmi_for_user function.
    """

    def test_recalculate_bmi_for_user_with_height(self, mock_db):
        """
        Test that a usable height issues a single bulk update and commit.
        """
        # Act
        health_weight_crud.recalculate_bmi_for_user(1, 175.0, mock_db)

        # Assert
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_recalculate_bmi_for_user_without_height(self, mock_db):
        """
        Test that a missing height still issues a single bulk update.
        """
        # Act
        health_weight_crud.recalculate_bmi_for_user(1, None, mock_db)

        # Assert
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_recalculate_bmi_for_user_exception(self, mock_db):
        """
        Test exception handling in recalculate_bmi_for_user.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_weight_crud.recalculate_bmi_for_user(1, 175.0, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()
