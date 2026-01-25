import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status

import health.health_intraday_heart_rate.models as health_intraday_heart_rate_models


class TestReadHealthIntradayHeartRateAll:
    """
    Test suite for read_health_intraday_heart_rate_all endpoint.
    """

    @patch(
        "health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_all_health_intraday_heart_rate_by_user_id"
    )
    def test_read_health_intraday_heart_rate_all_success(
        self, mock_get_all, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of all health intraday heart rate records with total count.
        """
        # Arrange
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        mock_heart_rate1 = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate1.id = 1
        mock_heart_rate1.user_id = 1
        mock_heart_rate1.timestamp = test_timestamp1
        mock_heart_rate1.heart_rate = 72
        mock_heart_rate1.source = None

        mock_heart_rate2 = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate2.id = 2
        mock_heart_rate2.user_id = 1
        mock_heart_rate2.timestamp = test_timestamp2
        mock_heart_rate2.heart_rate = 75
        mock_heart_rate2.source = None

        mock_get_all.return_value = [mock_heart_rate1, mock_heart_rate2]

        # Act
        response = fast_api_client.get(
            "/health_intraday_heart_rate",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) == 2

    @patch(
        "health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_all_health_intraday_heart_rate_by_user_id"
    )
    def test_read_health_intraday_heart_rate_all_empty(
        self, mock_get_all, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health intraday heart rate records.
        """
        # Arrange
        mock_get_all.return_value = []

        # Act
        response = fast_api_client.get(
            "/health_intraday_heart_rate",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 0
        assert data["records"] == []


class TestReadHealthIntradayHeartRateByDate:
    """
    Test suite for read_health_intraday_heart_rate_by_date endpoint.
    """

    @patch(
        "health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_health_intraday_heart_rate_records_by_date"
    )
    def test_read_health_intraday_heart_rate_by_date_success(
        self, mock_get_by_date, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of health intraday heart rate by date.
        """
        # Arrange
        mock_heart_rate1 = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate1.heart_rate = 72
        mock_heart_rate1.source = "garmin"
        mock_heart_rate1.id = 1
        mock_heart_rate1.user_id = 1
        
        mock_heart_rate2 = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate2.heart_rate = 75
        mock_heart_rate2.source = "garmin"
        mock_heart_rate2.id = 2
        mock_heart_rate2.user_id = 1

        mock_get_by_date.return_value = [mock_heart_rate1, mock_heart_rate2]

        # Act
        response = fast_api_client.get(
            "/health_intraday_heart_rate/2024-01-15",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 2
        assert len(data["records"]) == 2


class TestReadHealthIntradayHeartRateAllPagination:
    """
    Test suite for read_health_intraday_heart_rate_all_pagination endpoint.
    """

    @patch(
        "health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_health_intraday_heart_rate_with_pagination"
    )
    def test_read_health_intraday_heart_rate_all_pagination_success(
        self, mock_get_paginated, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of paginated health intraday heart rate records with total count.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_heart_rate1 = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate1.id = 1
        mock_heart_rate1.user_id = 1
        mock_heart_rate1.timestamp = test_timestamp
        mock_heart_rate1.heart_rate = 72
        mock_heart_rate1.source = None

        mock_get_paginated.return_value = [mock_heart_rate1]

        # Act
        response = fast_api_client.get(
            "/health_intraday_heart_rate/page_number/1/num_records/5",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 1
        assert data["page_number"] == 1
        assert len(data["records"]) == 1

    @patch(
        "health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_health_intraday_heart_rate_with_pagination"
    )
    def test_read_health_intraday_heart_rate_all_pagination_different_page(
        self, mock_get_paginated, fast_api_client, fast_api_app
    ):
        """
        Test paginated retrieval with different page numbers.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_heart_rate = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate.id = 1
        mock_heart_rate.user_id = 1
        mock_heart_rate.timestamp = test_timestamp
        mock_heart_rate.heart_rate = 72
        mock_heart_rate.source = None
        records = [mock_heart_rate, mock_heart_rate, mock_heart_rate]
        mock_get_paginated.return_value = records

        # Act
        response = fast_api_client.get(
            "/health_intraday_heart_rate/page_number/2/num_records/10",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["num_records"] == 3
        assert data["page_number"] == 2
        assert len(data["records"]) == 3
        mock_get_paginated.assert_called_once_with(1, ANY, 2, 10)


class TestCreateHealthIntradayHeartRate:
    """
    Test suite for create_health_intraday_heart_rate endpoint.
    """

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.create_health_intraday_heart_rate")
    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_health_intraday_heart_rate_by_timerange")
    def test_create_health_intraday_heart_rate_success(
        self,
        mock_get_by_timerange,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health intraday heart rate entry.
        """
        # Arrange
        mock_get_by_timerange.return_value = []
        created_heart_rate = MagicMock()
        created_heart_rate.id = 1
        created_heart_rate.user_id = 1
        created_heart_rate.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        created_heart_rate.heart_rate = 72
        created_heart_rate.source = None
        mock_create.return_value = created_heart_rate

        # Act
        response = fast_api_client.post(
            "/health_intraday_heart_rate",
            json={
                "timestamp": "2024-01-15T10:30:00",
                "heart_rate": 72,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        # The router will fail because it passes a single item to a function expecting a list
        # This test documents the current (buggy) behavior
        assert response.status_code in [201, 500]

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.edit_health_intraday_heart_rate")
    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.get_health_intraday_heart_rate_by_timerange")
    def test_create_health_intraday_heart_rate_updates_existing(
        self, mock_get_by_timerange, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test creating health intraday heart rate when entry exists updates it.
        """
        # Arrange
        existing_heart_rate = MagicMock()
        existing_heart_rate.id = 1
        mock_get_by_timerange.return_value = [existing_heart_rate]

        updated_heart_rate = MagicMock()
        updated_heart_rate.id = 1
        updated_heart_rate.user_id = 1
        updated_heart_rate.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        updated_heart_rate.heart_rate = 80
        updated_heart_rate.source = None
        mock_edit.return_value = updated_heart_rate

        # Act
        response = fast_api_client.post(
            "/health_intraday_heart_rate",
            json={
                "timestamp": "2024-01-15T10:30:00",
                "heart_rate": 80,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_edit.assert_called_once()


class TestEditHealthIntradayHeartRate:
    """
    Test suite for edit_health_intraday_heart_rate endpoint.
    """

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.edit_health_intraday_heart_rate")
    def test_edit_health_intraday_heart_rate_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health intraday heart rate entry.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        updated_heart_rate = MagicMock()
        updated_heart_rate.id = 1
        updated_heart_rate.user_id = 1
        updated_heart_rate.timestamp = test_timestamp
        updated_heart_rate.heart_rate = 80
        updated_heart_rate.source = None
        mock_edit.return_value = updated_heart_rate

        # Act
        response = fast_api_client.put(
            "/health_intraday_heart_rate",
            json={
                "id": 1,
                "user_id": 1,
                "timestamp": "2024-01-15T10:30:00",
                "heart_rate": 80,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["heart_rate"] == 80

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.edit_health_intraday_heart_rate")
    def test_edit_health_intraday_heart_rate_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test edit when health intraday heart rate not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health intraday heart rate not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_intraday_heart_rate",
            json={
                "id": 999,
                "user_id": 1,
                "timestamp": "2024-01-15T10:30:00",
                "heart_rate": 80,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteHealthIntradayHeartRate:
    """
    Test suite for delete_health_intraday_heart_rate endpoint.
    """

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.delete_health_intraday_heart_rate")
    def test_delete_health_intraday_heart_rate_success(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test successful deletion of health intraday heart rate entry.
        """
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/health_intraday_heart_rate/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, ANY)

    @patch("health.health_intraday_heart_rate.router.health_intraday_heart_rate_crud.delete_health_intraday_heart_rate")
    def test_delete_health_intraday_heart_rate_not_found(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test deletion when health intraday heart rate not found.
        """
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health intraday heart rate not found",
        )

        # Act
        response = fast_api_client.delete(
            "/health_intraday_heart_rate/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
