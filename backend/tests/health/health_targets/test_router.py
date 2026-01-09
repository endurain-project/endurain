import pytest
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status

import health.health_targets.schema as health_targets_schema
import health.health_targets.models as health_targets_models


class TestReadHealthTargetsAll:
    """
    Test suite for read_health_targets_all endpoint.
    """

    @patch(
        "health.health_targets.router.health_targets_crud.get_health_targets_by_user_id"
    )
    def test_read_health_targets_all_success(
        self, mock_get_targets, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of health targets.
        """
        # Arrange
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_targets.id = 1
        mock_targets.user_id = 1
        mock_targets.weight = 75.5
        mock_targets.steps = 10000
        mock_targets.sleep = 28800

        mock_get_targets.return_value = mock_targets

        # Act
        response = fast_api_client.get(
            "/health_targets/",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.5
        assert data["steps"] == 10000
        assert data["sleep"] == 28800

    @patch(
        "health.health_targets.router.health_targets_crud.get_health_targets_by_user_id"
    )
    def test_read_health_targets_all_not_found(
        self, mock_get_targets, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health targets.
        """
        # Arrange
        mock_get_targets.return_value = None

        # Act
        response = fast_api_client.get(
            "/health_targets/",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json() is None

    @patch(
        "health.health_targets.router.health_targets_crud.get_health_targets_by_user_id"
    )
    def test_read_health_targets_all_partial_data(
        self, mock_get_targets, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when health targets have partial data.
        """
        # Arrange
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_targets.id = 1
        mock_targets.user_id = 1
        mock_targets.weight = 75.5
        mock_targets.steps = None
        mock_targets.sleep = None

        mock_get_targets.return_value = mock_targets

        # Act
        response = fast_api_client.get(
            "/health_targets/",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.5
        assert data["steps"] is None
        assert data["sleep"] is None


class TestUpdateHealthTargets:
    """
    Test suite for update_health_targets endpoint.
    """

    @patch("health.health_targets.router.health_targets_crud.edit_health_target")
    def test_update_health_targets_success(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test successful update of health targets.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.weight = 80.0
        mock_updated_targets.steps = 12000
        mock_updated_targets.sleep = 32400

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.put(
            "/health_targets/",
            json={
                "id": 1,
                "user_id": 1,
                "weight": 80.0,
                "steps": 12000,
                "sleep": 32400,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 80.0
        assert data["steps"] == 12000
        assert data["sleep"] == 32400

    @patch("health.health_targets.router.health_targets_crud.edit_health_target")
    def test_update_health_targets_partial_update(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test partial update of health targets.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.weight = 75.0
        mock_updated_targets.steps = 10000
        mock_updated_targets.sleep = 28800

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.put(
            "/health_targets/",
            json={
                "id": 1,
                "user_id": 1,
                "weight": 75.0,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 75.0

    @patch("health.health_targets.router.health_targets_crud.edit_health_target")
    def test_update_health_targets_clear_values(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test clearing health target values by setting to null.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.weight = None
        mock_updated_targets.steps = None
        mock_updated_targets.sleep = None

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.put(
            "/health_targets/",
            json={
                "id": 1,
                "user_id": 1,
                "weight": None,
                "steps": None,
                "sleep": None,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] is None
        assert data["steps"] is None
        assert data["sleep"] is None

    @patch("health.health_targets.router.health_targets_crud.edit_health_target")
    def test_update_health_targets_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test update when health targets not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User health target not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_targets/",
            json={
                "id": 1,
                "user_id": 1,
                "weight": 80.0,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404

    @patch("health.health_targets.router.health_targets_crud.edit_health_target")
    def test_update_health_targets_with_all_fields(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test update with all fields provided.
        """
        # Arrange
        mock_updated_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_updated_targets.id = 1
        mock_updated_targets.user_id = 1
        mock_updated_targets.weight = 85.5
        mock_updated_targets.steps = 15000
        mock_updated_targets.sleep = 36000

        mock_edit.return_value = mock_updated_targets

        # Act
        response = fast_api_client.put(
            "/health_targets/",
            json={
                "id": 1,
                "user_id": 1,
                "weight": 85.5,
                "steps": 15000,
                "sleep": 36000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 85.5
        assert data["steps"] == 15000
        assert data["sleep"] == 36000
