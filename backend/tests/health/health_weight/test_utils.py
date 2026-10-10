from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.utils as health_weight_utils


class TestCalculateBMI:
    """
    Test suite for calculate_bmi function.
    """

    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
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

        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.0, bmi=None)

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is not None
        expected_bmi = 75.0 / ((175 / 100) ** 2)
        assert abs(result.bmi - expected_bmi) < 0.01
        mock_get_user.assert_called_once_with(user_id, mock_db)

    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
    def test_calculate_bmi_user_not_found(self, mock_get_user):
        """
        Test BMI calculation when user not found.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_user.return_value = None

        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.0, bmi=None)

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
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

        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.0, bmi=None)

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
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

        health_weight = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=None, bmi=None)

        # Act
        result = health_weight_utils.calculate_bmi(health_weight, user_id, mock_db)

        # Assert
        assert result.bmi is None

    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
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

    @patch("modules.health.health_weight.utils.health_weight_crud.recalculate_bmi_for_user")
    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
    def test_delegates_with_user_height(self, mock_get_user, mock_recalculate):
        """
        Test that recalculation delegates using the user's height.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_user = MagicMock()
        mock_user.height = 175
        mock_get_user.return_value = mock_user

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_get_user.assert_called_once_with(user_id, mock_db)
        mock_recalculate.assert_called_once_with(user_id, 175.0, mock_db)

    @patch("modules.health.health_weight.utils.health_weight_crud.recalculate_bmi_for_user")
    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
    def test_delegates_with_none_height_when_user_has_no_height(self, mock_get_user, mock_recalculate):
        """
        Test delegation passes None height when the user has no height.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_user = MagicMock()
        mock_user.height = None
        mock_get_user.return_value = mock_user

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_recalculate.assert_called_once_with(user_id, None, mock_db)

    @patch("modules.health.health_weight.utils.health_weight_crud.recalculate_bmi_for_user")
    @patch("modules.health.health_weight.utils.users_crud.get_user_by_id")
    def test_delegates_with_none_height_when_user_missing(self, mock_get_user, mock_recalculate):
        """
        Test delegation passes None height when the user is not found.
        """
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_user.return_value = None

        # Act
        health_weight_utils.calculate_bmi_all_user_entries(user_id, mock_db)

        # Assert
        mock_recalculate.assert_called_once_with(user_id, None, mock_db)
