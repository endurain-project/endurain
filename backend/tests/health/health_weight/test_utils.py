import pytest
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

import health.health_weight.utils as health_weight_utils
import health.health_weight.schema as health_weight_schema
import users.users.schema as user_schema


class TestCalculateBMI:
    """
    Test suite for calculate_bmi function.
    """

    @patch("health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_success(self, mock_get_user):
        """
        Test successful BMI calculation.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_user = MagicMock()
        mock_user.height = 175
        mock_get_user.return_value = mock_user

        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=75.0, bmi=None
        )

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is not None
        expected_bmi = 75.0 / ((175 / 100) ** 2)
        assert abs(result.bmi - expected_bmi) < 0.01
        mock_get_user.assert_called_once_with(user_id, mock_db)

    @patch("health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_user_not_found(self, mock_get_user):
        """
        Test BMI calculation when user not found.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_user.return_value = None

        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=75.0, bmi=None
        )

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_no_height(self, mock_get_user):
        """
        Test BMI calculation when user has no height.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_user = MagicMock()
        mock_user.height = None
        mock_get_user.return_value = mock_user

        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=75.0, bmi=None
        )

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_no_weight(self, mock_get_user):
        """
        Test BMI calculation when health weight has no weight.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_user = MagicMock()
        mock_user.height = 175
        mock_get_user.return_value = mock_user

        health_weight = health_weight_schema.HealthWeightCreate(
            date=datetime_date(2024, 1, 15), weight=None, bmi=None
        )

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_various_heights_and_weights(self, mock_get_user):
        """
        Test BMI calculation with various heights and weights.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        test_cases = [
            (180, 80.0, 80.0 / ((180 / 100) ** 2)),
            (165, 60.0, 60.0 / ((165 / 100) ** 2)),
            (190, 95.0, 95.0 / ((190 / 100) ** 2)),
        ]

        for height, weight, expected_bmi in test_cases:
            # Arrange
            mock_user = MagicMock()
            mock_user.height = height
            mock_get_user.return_value = mock_user

            health_weight = health_weight_schema.HealthWeightCreate(
                date=datetime_date(2024, 1, 15),
                weight=weight,
                bmi=None,
            )

            # Act
            result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

            # Assert
            assert result.bmi is not None
            assert abs(result.bmi - expected_bmi) < 0.01


class TestCalculateBMIAllUserEntries:
    """
    Test suite for calculate_bmi_all_user_entries function.
    """

    @patch("health.health_weight.utils.health_weight_crud.edit_health_weight")
    @patch(
        "health.health_weight.utils.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    @patch("health.health_weight.utils.calculate_bmi")
    def test_calculate_bmi_all_user_entries_success(
        self, mock_calculate_bmi, mock_get_all, mock_edit
    ):
        """
        Test successful BMI calculation for all user entries.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_weight1 = MagicMock()
        mock_weight1.id = 1
        mock_weight1.user_id = user_id
        mock_weight1.date = datetime_date(2024, 1, 15)
        mock_weight1.weight = 75.0
        mock_weight1.bmi = None
        mock_weight1.body_fat = None
        mock_weight1.body_water = None
        mock_weight1.bone_mass = None
        mock_weight1.muscle_mass = None
        mock_weight1.physique_rating = None
        mock_weight1.visceral_fat = None
        mock_weight1.metabolic_age = None
        mock_weight1.source = "garmin"

        mock_weight2 = MagicMock()
        mock_weight2.id = 2
        mock_weight2.user_id = user_id
        mock_weight2.date = datetime_date(2024, 1, 16)
        mock_weight2.weight = 74.5
        mock_weight2.bmi = None
        mock_weight2.body_fat = None
        mock_weight2.body_water = None
        mock_weight2.bone_mass = None
        mock_weight2.muscle_mass = None
        mock_weight2.physique_rating = None
        mock_weight2.visceral_fat = None
        mock_weight2.metabolic_age = None
        mock_weight2.source = "garmin"

        mock_get_all.return_value = [mock_weight1, mock_weight2]

        calculated_weight1 = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=user_id,
            date=datetime_date(2024, 1, 15),
            weight=75.0,
            bmi=24.5,
            source="garmin",
        )
        calculated_weight2 = health_weight_schema.HealthWeightUpdate(
            id=2,
            user_id=user_id,
            date=datetime_date(2024, 1, 16),
            weight=74.5,
            bmi=24.3,
            source="garmin",
        )

        mock_calculate_bmi.side_effect = [
            calculated_weight1,
            calculated_weight2,
        ]

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_get_all.assert_called_once_with(user_id, mock_db)
        assert mock_calculate_bmi.call_count == 2
        assert mock_edit.call_count == 2

    @patch(
        "health.health_weight.utils.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    def test_calculate_bmi_all_user_entries_no_entries(self, mock_get_all):
        """
        Test BMI calculation when user has no entries.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_all.return_value = None

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_get_all.assert_called_once_with(user_id, mock_db)

    @patch(
        "health.health_weight.utils.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    def test_calculate_bmi_all_user_entries_empty_list(self, mock_get_all):
        """
        Test BMI calculation when user has empty list of entries.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_all.return_value = []

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_get_all.assert_called_once_with(user_id, mock_db)

    @patch("health.health_weight.utils.health_weight_crud.edit_health_weight")
    @patch(
        "health.health_weight.utils.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    @patch("health.health_weight.utils.calculate_bmi")
    def test_calculate_bmi_all_user_entries_with_all_fields(
        self, mock_calculate_bmi, mock_get_all, mock_edit
    ):
        """
        Test BMI calculation for entries with all fields populated.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)

        mock_weight = MagicMock()
        mock_weight.id = 1
        mock_weight.user_id = user_id
        mock_weight.date = datetime_date(2024, 1, 15)
        mock_weight.weight = 75.0
        mock_weight.bmi = 24.0
        mock_weight.body_fat = 18.5
        mock_weight.body_water = 60.0
        mock_weight.bone_mass = 3.5
        mock_weight.muscle_mass = 62.0
        mock_weight.physique_rating = 7
        mock_weight.visceral_fat = 5.0
        mock_weight.metabolic_age = 25
        mock_weight.source = "garmin"

        mock_get_all.return_value = [mock_weight]

        calculated_weight = health_weight_schema.HealthWeightUpdate(
            id=1,
            user_id=user_id,
            date=datetime_date(2024, 1, 15),
            weight=75.0,
            bmi=24.5,
            source="garmin",
        )
        mock_calculate_bmi.return_value = calculated_weight

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        assert mock_calculate_bmi.call_count == 1
        assert mock_edit.call_count == 1
