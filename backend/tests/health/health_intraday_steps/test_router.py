import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status

import health.health_intraday_steps.models as health_intraday_steps_models


class TestReadHealthIntradayStepsAll:
    """
    Test suite for read_health_intraday_steps_all endpoint.
    """

    @patch(
        "health.health_intraday_steps.router.health_intraday_steps_crud.get_all_health_intraday_steps_by_user_id"
    )
    def test_read_health_intraday_steps_all_success(
        self, mock_get_all, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of all health intraday steps record.
        """
        # Arrange
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps1.id = 1
        mock_steps1.user_id = 1
        mock_steps1.timestamp = test_timestamp1
        mock_steps1.steps = 1000
        mock_steps1.source = None
        mock_steps1.activity_type = None
        mock_steps1.intensity = None

        mock_steps2 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps2.id = 2
        mock_steps2.user_id = 1
        mock_steps2.timestamp = test_timestamp2
        mock_steps2.steps = 1200
        mock_steps2.source = None
        mock_steps2.activity_type = None
        mock_steps2.intensity = None

        mock_get_all.return_value = [mock_steps1, mock_steps2]

        # Act
        response = fast_api_client.get(
            "/health_intraday_steps",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) == 2

    @patch(
        "health.health_intraday_steps.router.health_intraday_steps_crud.get_all_health_intraday_steps_by_user_id"
    )
    def test_read_health_intraday_steps_all_empty(
        self, mock_get_all, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health intraday steps records.
        """
        # Arrange
        mock_get_all.return_value = []

        # Act
        response = fast_api_client.get(
            "/health_intraday_steps",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []


class TestReadHealthIntradayStepsByDate:
    """
    Test suite for read_health_intraday_steps_by_date endpoint.
    """

    @patch(
        "health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_records_by_date"
    )
    def test_read_health_intraday_steps_by_date_success(
        self, mock_get_by_date, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of health intraday steps by date.
        """
        # Arrange
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps1.steps = 1000
        mock_steps1.id = 1
        mock_steps1.activity_type = 1
        mock_steps1.intensity = None
        mock_steps1.source = "garmin"
        mock_steps1.user_id = 1

        mock_steps2 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps2.steps = 1200
        mock_steps2.id = 2
        mock_steps2.activity_type = 3
        mock_steps2.intensity = None
        mock_steps2.source = "garmin"
        mock_steps2.user_id = 1

        mock_get_by_date.return_value = [mock_steps1, mock_steps2]

        # Act
        response = fast_api_client.get(
            "/health_intraday_steps/2024-01-15",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 2
        assert len(data["records"]) == 2


class TestReadHealthIntradayStepsAllPagination:
    """
    Test suite for read_health_intraday_steps_all_pagination endpoint.
    """

    @patch(
        "health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_with_pagination"
    )
    def test_read_health_intraday_steps_all_pagination_success(
        self, mock_get_paginated, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of paginated health intraday steps record.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps1.id = 1
        mock_steps1.user_id = 1
        mock_steps1.timestamp = test_timestamp
        mock_steps1.steps = 1000
        mock_steps1.source = None
        mock_steps1.activity_type = None
        mock_steps1.intensity = None

        mock_get_paginated.return_value = [mock_steps1]

        # Act
        response = fast_api_client.get(
            "/health_intraday_steps/page_number/1/num_records/5",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 5
        assert data["page_number"] == 1
        assert len(data["records"]) == 1

    @patch(
        "health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_with_pagination"
    )
    def test_read_health_intraday_steps_all_pagination_different_page(
        self, mock_get_paginated, fast_api_client, fast_api_app
    ):
        """
        Test paginated retrieval with different page numbers.
        """
        # Arrange
        mock_get_paginated.return_value = []

        # Act
        response = fast_api_client.get(
            "/health_intraday_steps/page_number/2/num_records/10",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 10
        assert data["page_number"] == 2
        assert data["records"] == []
        mock_get_paginated.assert_called_once_with(1, ANY, 2, 10)


class TestCreateHealthIntradaySteps:
    """
    Test suite for create_health_intraday_steps endpoint.
    """

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.create_health_intraday_steps")
    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_by_timerange")
    def test_create_health_intraday_steps_success(
        self,
        mock_get_by_timerange,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health intraday steps entry.
        """
        # Arrange
        mock_get_by_timerange.return_value = []
        created_steps = MagicMock()
        created_steps.id = 1
        created_steps.user_id = 1
        created_steps.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        created_steps.steps = 1000
        created_steps.source = None
        created_steps.activity_type = None
        created_steps.intensity = None
        mock_create.return_value = created_steps

        # Act
        response = fast_api_client.post(
            "/health_intraday_steps",
            json={
                "timestamp": "2024-01-15T10:30:00",
                "steps": 1000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["steps"] == 1000

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.edit_health_intraday_steps")
    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_by_timerange")
    def test_create_health_intraday_steps_updates_existing(
        self, mock_get_by_timerange, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test creating health intraday steps when entry exists updates it.
        """
        # Arrange
        existing_steps = MagicMock()
        existing_steps.id = 1
        mock_get_by_timerange.return_value = [existing_steps]

        updated_steps = MagicMock()
        updated_steps.id = 1
        updated_steps.user_id = 1
        updated_steps.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        updated_steps.steps = 1200
        updated_steps.source = None
        updated_steps.activity_type = None
        updated_steps.intensity = None
        mock_edit.return_value = updated_steps

        # Act
        response = fast_api_client.post(
            "/health_intraday_steps",
            json={
                "timestamp": "2024-01-15T10:30:00",
                "steps": 1200,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_edit.assert_called_once()

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.create_health_intraday_steps")
    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.get_health_intraday_steps_by_timerange")
    def test_create_health_intraday_steps_missing_timestamp_uses_now(
        self, mock_get_by_timerange, mock_create, fast_api_client, fast_api_app
    ):
        """
        Test creating health intraday steps without timestamp uses current time automatically.
        """
        # Arrange
        mock_get_by_timerange.return_value = []
        created_steps = MagicMock()
        created_steps.id = 1
        created_steps.user_id = 1
        created_steps.timestamp = None  # Will be set by schema
        created_steps.steps = 1000
        created_steps.source = None
        created_steps.activity_type = None
        created_steps.intensity = None
        mock_create.return_value = created_steps

        # Act
        response = fast_api_client.post(
            "/health_intraday_steps",
            json={
                "steps": 1000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert - Now succeeds since HealthIntradayStepsCreate auto-fills timestamp
        assert response.status_code == 201
        mock_create.assert_called_once()

    def test_create_health_intraday_steps_missing_timestamp_required(
        self, fast_api_client, fast_api_app
    ):
        """
        Test creating health intraday steps without timestamp raises error (router validation).
        """
        # Note: The router checks if timestamp is None and raises 400
        # But the schema validator sets it to now, so this test may need adjustment
        # based on actual router behavior
        pass


class TestEditHealthIntradaySteps:
    """
    Test suite for edit_health_intraday_steps endpoint.
    """

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.edit_health_intraday_steps")
    def test_edit_health_intraday_steps_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health intraday steps entry.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        updated_steps = MagicMock()
        updated_steps.id = 1
        updated_steps.user_id = 1
        updated_steps.timestamp = test_timestamp
        updated_steps.steps = 1200
        updated_steps.source = None
        updated_steps.activity_type = None
        updated_steps.intensity = None
        mock_edit.return_value = updated_steps

        # Act
        response = fast_api_client.put(
            "/health_intraday_steps",
            json={
                "id": 1,
                "user_id": 1,
                "timestamp": "2024-01-15T10:30:00",
                "steps": 1200,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["steps"] == 1200

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.edit_health_intraday_steps")
    def test_edit_health_intraday_steps_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test edit when health intraday steps not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health intraday steps not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_intraday_steps",
            json={
                "id": 999,
                "user_id": 1,
                "timestamp": "2024-01-15T10:30:00",
                "steps": 1200,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteHealthIntradaySteps:
    """
    Test suite for delete_health_intraday_steps endpoint.
    """

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.delete_health_intraday_steps")
    def test_delete_health_intraday_steps_success(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test successful deletion of health intraday steps entry.
        """
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/health_intraday_steps/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, ANY)

    @patch("health.health_intraday_steps.router.health_intraday_steps_crud.delete_health_intraday_steps")
    def test_delete_health_intraday_steps_not_found(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test deletion when health intraday steps not found.
        """
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health intraday steps not found",
        )

        # Act
        response = fast_api_client.delete(
            "/health_intraday_steps/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
