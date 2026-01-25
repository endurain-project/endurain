import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, ANY, mock_open
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import io

import health.router as health_router
import health.schema as health_schema
import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema


class TestCreateHealthWithUploadedFile:
    """
    Test suite for create_health_with_uploaded_file endpoint.
    """

    @patch("health.router.health_utils.parse_and_store_health_from_uploaded_file")
    def test_create_health_with_uploaded_file_success(
        self, mock_parse_and_store, fast_api_client, fast_api_app
    ):
        """
        Test successful creation of health data from uploaded file.
        """
        # Arrange
        mock_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            steps=1000,
            source="garmin",
        )
        mock_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            heart_rate=75,
            source="garmin",
        )
        mock_response = health_schema.HealthImportResponse(
            created_intraday_step_records=[mock_steps],
            created_intraday_heart_rate_records=[mock_heart_rate],
        )
        mock_parse_and_store.return_value = mock_response

        # Create a mock file
        file_content = b"test file content"
        file = ("test.fit", io.BytesIO(file_content), "application/octet-stream")

        # Act
        response = fast_api_client.post(
            "/health/create/upload",
            files={"file": file},
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "created_intraday_step_records" in data
        assert "created_intraday_heart_rate_records" in data
        mock_parse_and_store.assert_called_once()

    @patch("health.router.health_utils.parse_and_store_health_from_uploaded_file")
    def test_create_health_with_uploaded_file_error(
        self, mock_parse_and_store, fast_api_client, fast_api_app
    ):
        """
        Test error handling when file processing fails.
        """
        # Arrange
        mock_parse_and_store.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        )

        # Create a mock file
        file_content = b"test file content"
        file = ("test.fit", io.BytesIO(file_content), "application/octet-stream")

        # Act
        response = fast_api_client.post(
            "/health/create/upload",
            files={"file": file},
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 500
        mock_parse_and_store.assert_called_once()

    @patch("health.router.health_utils.parse_and_store_health_from_uploaded_file")
    def test_create_health_with_uploaded_file_generic_exception(
        self, mock_parse_and_store, fast_api_client, fast_api_app
    ):
        """
        Test error handling when a generic exception occurs.
        """
        # Arrange
        mock_parse_and_store.side_effect = ValueError("Some error")

        # Create a mock file
        file_content = b"test file content"
        file = ("test.fit", io.BytesIO(file_content), "application/octet-stream")

        # Act
        response = fast_api_client.post(
            "/health/create/upload",
            files={"file": file},
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 500
        mock_parse_and_store.assert_called_once()