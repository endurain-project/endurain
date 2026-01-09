import pytest
from datetime import datetime, date as datetime_date
from decimal import Decimal
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status

import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.models as health_sleep_models


class TestReadHealthSleepAll:
    """
    Test suite for read_health_sleep_all endpoint.
    """

    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_number")
    @patch(
        "health.health_sleep.router.health_sleep_crud.get_all_health_sleep_by_user_id"
    )
    def test_read_health_sleep_all_success(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of all health sleep records with total count.
        """
        # Arrange
        mock_sleep1 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_sleep1.id = 1
        mock_sleep1.user_id = 1
        mock_sleep1.date = datetime_date(2024, 1, 15)
        mock_sleep1.sleep_start_time_gmt = datetime(2024, 1, 14, 22, 0, 0)
        mock_sleep1.sleep_end_time_gmt = datetime(2024, 1, 15, 6, 0, 0)
        mock_sleep1.sleep_start_time_local = None
        mock_sleep1.sleep_end_time_local = None
        mock_sleep1.total_sleep_seconds = 28800
        mock_sleep1.nap_time_seconds = None
        mock_sleep1.unmeasurable_sleep_seconds = None
        mock_sleep1.deep_sleep_seconds = 7200
        mock_sleep1.light_sleep_seconds = 14400
        mock_sleep1.rem_sleep_seconds = 7200
        mock_sleep1.awake_sleep_seconds = 0
        mock_sleep1.avg_heart_rate = 55
        mock_sleep1.min_heart_rate = 45
        mock_sleep1.max_heart_rate = 75
        mock_sleep1.avg_spo2 = 97
        mock_sleep1.lowest_spo2 = 95
        mock_sleep1.highest_spo2 = 99
        mock_sleep1.avg_respiration = None
        mock_sleep1.lowest_respiration = None
        mock_sleep1.highest_respiration = None
        mock_sleep1.avg_stress_level = None
        mock_sleep1.awake_count = 2
        mock_sleep1.restless_moments_count = 5
        mock_sleep1.sleep_score_overall = 85
        mock_sleep1.sleep_score_duration = "GOOD"
        mock_sleep1.sleep_score_quality = "GOOD"
        mock_sleep1.garminconnect_sleep_id = None
        mock_sleep1.sleep_stages = None
        mock_sleep1.source = None
        mock_sleep1.hrv_status = None
        mock_sleep1.resting_heart_rate = 50
        mock_sleep1.avg_skin_temp_deviation = None
        mock_sleep1.awake_count_score = None
        mock_sleep1.rem_percentage_score = None
        mock_sleep1.deep_percentage_score = None
        mock_sleep1.light_percentage_score = None
        mock_sleep1.avg_sleep_stress = None
        mock_sleep1.sleep_stress_score = None

        mock_get_all.return_value = [mock_sleep1]
        mock_get_number.return_value = 1

        # Act
        response = fast_api_client.get(
            "/health_sleep",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["records"]) == 1

    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_number")
    @patch(
        "health.health_sleep.router.health_sleep_crud.get_all_health_sleep_by_user_id"
    )
    def test_read_health_sleep_all_empty(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health sleep records.
        """
        # Arrange
        mock_get_all.return_value = []
        mock_get_number.return_value = 0

        # Act
        response = fast_api_client.get(
            "/health_sleep",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadHealthSleepAllPagination:
    """
    Test suite for read_health_sleep_all_pagination endpoint.
    """

    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_number")
    @patch(
        "health.health_sleep.router.health_sleep_crud.get_health_sleep_with_pagination"
    )
    def test_read_health_sleep_all_pagination_success(
        self, mock_get_paginated, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of paginated health sleep records with total count.
        """
        # Arrange
        mock_sleep1 = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_sleep1.id = 1
        mock_sleep1.user_id = 1
        mock_sleep1.date = datetime_date(2024, 1, 15)
        mock_sleep1.sleep_start_time_gmt = None
        mock_sleep1.sleep_end_time_gmt = None
        mock_sleep1.sleep_start_time_local = None
        mock_sleep1.sleep_end_time_local = None
        mock_sleep1.total_sleep_seconds = 28800
        mock_sleep1.nap_time_seconds = None
        mock_sleep1.unmeasurable_sleep_seconds = None
        mock_sleep1.deep_sleep_seconds = None
        mock_sleep1.light_sleep_seconds = None
        mock_sleep1.rem_sleep_seconds = None
        mock_sleep1.awake_sleep_seconds = None
        mock_sleep1.avg_heart_rate = None
        mock_sleep1.min_heart_rate = None
        mock_sleep1.max_heart_rate = None
        mock_sleep1.avg_spo2 = None
        mock_sleep1.lowest_spo2 = None
        mock_sleep1.highest_spo2 = None
        mock_sleep1.avg_respiration = None
        mock_sleep1.lowest_respiration = None
        mock_sleep1.highest_respiration = None
        mock_sleep1.avg_stress_level = None
        mock_sleep1.awake_count = None
        mock_sleep1.restless_moments_count = None
        mock_sleep1.sleep_score_overall = None
        mock_sleep1.sleep_score_duration = None
        mock_sleep1.sleep_score_quality = None
        mock_sleep1.garminconnect_sleep_id = None
        mock_sleep1.sleep_stages = None
        mock_sleep1.source = None
        mock_sleep1.hrv_status = None
        mock_sleep1.resting_heart_rate = None
        mock_sleep1.avg_skin_temp_deviation = None
        mock_sleep1.awake_count_score = None
        mock_sleep1.rem_percentage_score = None
        mock_sleep1.deep_percentage_score = None
        mock_sleep1.light_percentage_score = None
        mock_sleep1.avg_sleep_stress = None
        mock_sleep1.sleep_stress_score = None

        mock_get_paginated.return_value = [mock_sleep1]
        mock_get_number.return_value = 10

        # Act
        response = fast_api_client.get(
            "/health_sleep/page_number/1/num_records/5",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert data["num_records"] == 5
        assert data["page_number"] == 1
        assert len(data["records"]) == 1

    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_number")
    @patch(
        "health.health_sleep.router.health_sleep_crud.get_health_sleep_with_pagination"
    )
    def test_read_health_sleep_all_pagination_different_page(
        self, mock_get_paginated, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test paginated retrieval with different page numbers.
        """
        # Arrange
        mock_get_paginated.return_value = []
        mock_get_number.return_value = 20

        # Act
        response = fast_api_client.get(
            "/health_sleep/page_number/2/num_records/10",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 20
        assert data["num_records"] == 10
        assert data["page_number"] == 2
        assert data["records"] == []
        mock_get_paginated.assert_called_once_with(1, ANY, 2, 10)


class TestCreateHealthSleep:
    """
    Test suite for create_health_sleep endpoint.
    """

    @patch("health.health_sleep.router.health_sleep_crud.create_health_sleep")
    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_by_date")
    def test_create_health_sleep_success(
        self,
        mock_get_by_date,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health sleep entry.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
        )
        mock_create.return_value = created_sleep

        # Act
        response = fast_api_client.post(
            "/health_sleep",
            json={
                "date": "2024-01-15",
                "total_sleep_seconds": 28800,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["total_sleep_seconds"] == 28800

    @patch("health.health_sleep.router.health_sleep_crud.edit_health_sleep")
    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_by_date")
    def test_create_health_sleep_updates_existing(
        self, mock_get_by_date, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test creating health sleep when entry exists updates it.
        """
        # Arrange
        existing_sleep = MagicMock()
        existing_sleep.id = 1
        mock_get_by_date.return_value = existing_sleep

        updated_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=32400,
        )
        mock_edit.return_value = updated_sleep

        # Act
        response = fast_api_client.post(
            "/health_sleep",
            json={
                "date": "2024-01-15",
                "total_sleep_seconds": 32400,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_edit.assert_called_once()

    @patch("health.health_sleep.router.health_sleep_crud.create_health_sleep")
    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_by_date")
    def test_create_health_sleep_missing_date_uses_today(
        self, mock_get_by_date, mock_create, fast_api_client, fast_api_app
    ):
        """
        Test creating health sleep without date uses today's date automatically.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date.today(),
            total_sleep_seconds=28800,
        )
        mock_create.return_value = created_sleep

        # Act
        response = fast_api_client.post(
            "/health_sleep",
            json={
                "total_sleep_seconds": 28800,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert - Now succeeds since HealthSleepCreate auto-fills date
        assert response.status_code == 201
        mock_create.assert_called_once()

    @patch("health.health_sleep.sleep_scoring._calculate_and_set_sleep_scores")
    @patch("health.health_sleep.router.health_sleep_crud.create_health_sleep")
    @patch("health.health_sleep.router.health_sleep_crud.get_health_sleep_by_date")
    def test_create_health_sleep_calls_scoring(
        self, mock_get_by_date, mock_create, mock_scoring, fast_api_client, fast_api_app
    ):
        """
        Test creating health sleep calls sleep scoring function.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
        )
        mock_create.return_value = created_sleep

        # Act
        response = fast_api_client.post(
            "/health_sleep",
            json={
                "date": "2024-01-15",
                "total_sleep_seconds": 28800,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_scoring.assert_called_once()


class TestEditHealthSleep:
    """
    Test suite for edit_health_sleep endpoint.
    """

    @patch("health.health_sleep.router.health_sleep_crud.edit_health_sleep")
    def test_edit_health_sleep_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health sleep entry.
        """
        # Arrange
        updated_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=32400,
        )
        mock_edit.return_value = updated_sleep

        # Act
        response = fast_api_client.put(
            "/health_sleep",
            json={
                "id": 1,
                "user_id": 1,
                "date": "2024-01-15",
                "total_sleep_seconds": 32400,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_sleep_seconds"] == 32400

    @patch("health.health_sleep.router.health_sleep_crud.edit_health_sleep")
    def test_edit_health_sleep_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test edit when health sleep not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health sleep not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_sleep",
            json={
                "id": 999,
                "user_id": 1,
                "date": "2024-01-15",
                "total_sleep_seconds": 32400,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestEditHealthSleepScoringIntegration:
    """
    Test suite for edit_health_sleep endpoint scoring integration.
    """

    @patch("health.health_sleep.sleep_scoring._calculate_and_set_sleep_scores")
    @patch("health.health_sleep.router.health_sleep_crud.edit_health_sleep")
    def test_edit_health_sleep_calls_scoring(
        self, mock_edit, mock_scoring, fast_api_client, fast_api_app
    ):
        """
        Test editing health sleep calls sleep scoring function.
        """
        # Arrange
        updated_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=32400,
        )
        mock_edit.return_value = updated_sleep

        # Act
        response = fast_api_client.put(
            "/health_sleep",
            json={
                "id": 1,
                "user_id": 1,
                "date": "2024-01-15",
                "total_sleep_seconds": 32400,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        mock_scoring.assert_called_once()


class TestDeleteHealthSleep:
    """
    Test suite for delete_health_sleep endpoint.
    """

    @patch("health.health_sleep.router.health_sleep_crud.delete_health_sleep")
    def test_delete_health_sleep_success(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test successful deletion of health sleep entry.
        """
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/health_sleep/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, ANY)

    @patch("health.health_sleep.router.health_sleep_crud.delete_health_sleep")
    def test_delete_health_sleep_not_found(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test deletion when health sleep not found.
        """
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health sleep with id 999 for user 1 not found",
        )

        # Act
        response = fast_api_client.delete(
            "/health_sleep/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
