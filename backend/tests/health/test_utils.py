import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, mock_open, ANY
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import io
import os
import asyncio

import health.utils as health_utils
import health.schema as health_schema
import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_steps.models as health_intraday_steps_models
import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema
import health.health_intraday_heart_rate.models as health_intraday_heart_rate_models
import health.health_sleep.models as health_sleep_models


class TestCreateHealthImportResponse:
    """
    Test suite for create_health_import_response function.
    """

    def test_create_health_import_response_success(self):
        """
        Test successful creation of health import response.
        """
        # Arrange
        mock_step = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_step.id = 1
        mock_step.user_id = 1
        mock_step.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_step.steps = 1000
        mock_step.source = "garmin"
        mock_step.activity_type = 1
        mock_step.intensity = None

        mock_heart_rate = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate.id = 1
        mock_heart_rate.user_id = 1
        mock_heart_rate.timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_heart_rate.heart_rate = 75
        mock_heart_rate.source = "garmin"

        mock_sleep = MagicMock(spec=health_sleep_models.HealthSleep)
        mock_sleep.id = 1
        mock_sleep.user_id = 2
        mock_sleep.date = datetime(2024, 1, 15).date()
        mock_sleep.sleep_start_time_gmt = datetime(2024, 1, 15, 10, 30, 0)
        mock_sleep.sleep_end_time_gmt = datetime(2024, 1, 16, 10, 30, 0)
        mock_sleep.sleep_start_time_local = datetime(2024, 1, 15, 10, 30, 0)
        mock_sleep.sleep_end_time_local = datetime(2024, 1, 16, 10, 30, 0)
        mock_sleep.resting_heart_rate = 50
        mock_sleep.total_sleep_seconds = 0
        mock_sleep.nap_time_seconds = 0
        mock_sleep.unmeasurable_sleep_seconds = 0
        mock_sleep.deep_sleep_seconds = 0
        mock_sleep.light_sleep_seconds = 0
        mock_sleep.rem_sleep_seconds = 0
        mock_sleep.awake_sleep_seconds = 0
        mock_sleep.avg_heart_rate = 65
        mock_sleep.min_heart_rate = 60
        mock_sleep.max_heart_rate = 70
        mock_sleep.avg_spo2 = 80
        mock_sleep.lowest_spo2 = 70
        mock_sleep.highest_spo2 = 90
        mock_sleep.avg_respiration = 0
        mock_sleep.lowest_respiration = 0
        mock_sleep.highest_respiration = 0
        mock_sleep.avg_stress_level = 0
        mock_sleep.awake_count = 0
        mock_sleep.restless_moments_count = 0
        mock_sleep.sleep_score_overall = 0
        mock_sleep.sleep_score_duration = "GOOD"
        mock_sleep.sleep_score_quality = "GOOD"
        mock_sleep.garminconnect_sleep_id = "garmin_123"
        mock_sleep.source = "garmin"
        mock_sleep.hrv_status = "BALANCED"
        mock_sleep.awake_count_score = "GOOD"
        mock_sleep.rem_percentage_score = "GOOD"
        mock_sleep.deep_percentage_score = "GOOD"
        mock_sleep.light_percentage_score = "GOOD"
        mock_sleep.avg_sleep_stress = 0
        mock_sleep.sleep_stress_score = "GOOD"

        # Act
        result = health_utils.create_health_import_response([mock_step], [mock_heart_rate], mock_sleep)

        # Assert
        assert isinstance(result, health_schema.HealthImportResponse)
        assert len(result.created_intraday_step_records) == 1
        assert len(result.created_intraday_heart_rate_records) == 1

    def test_create_health_import_response_empty_lists(self):
        """
        Test creation of health import response with empty lists.
        """
        # Act
        result = health_utils.create_health_import_response([], [], None)

        # Assert
        assert len(result.created_intraday_step_records) == 0
        assert len(result.created_intraday_heart_rate_records) == 0
        assert result.updated_sleep is None

class TestProcessInfo:
    """
    Test suite for process_info function.
    """

    def test_process_info_success(self):
        """
        Test successful processing of parsed info.
        """
        # Arrange
        parsed_info = {
            "intraday_steps": [
                {"timestamp": datetime(2024, 1, 15, 10, 30, 0), "steps": 1000, "distance": 1,   "intensity": 5, "activity_type": "running"},
                {"timestamp": datetime(2024, 1, 15, 10, 31, 0), "steps": 1200, "distance": 1.2, "intensity": 6, "activity_type": "running"},
            ],
            "intraday_heart_rate": [
                {"timestamp": datetime(2024, 1, 15, 10, 30, 0), "heart_rate": 75},
                {"timestamp": datetime(2024, 1, 15, 10, 31, 0), "heart_rate": 80},
            ],
            "resting_heart_rate": {
                "timestamp": datetime(2024, 1, 15, 10, 30, 0),
                "resting_heart_rate": 60, 
                "current_day_resting_heart_rate": 65
            },
        }

        # Act
        intraday_steps, intraday_heart_rate, resting_heart_rate = health_utils.process_info(parsed_info)

        # Assert
        assert len(intraday_steps) == 2
        assert len(intraday_heart_rate) == 2
        assert resting_heart_rate == 60
        # Check that steps were converted to deltas
        assert intraday_steps[0].steps == 1000  # First step is the delta from 0
        assert intraday_steps[1].steps == 200  # Second step is the delta from 1000

    def test_process_info_empty_data(self):
        """
        Test processing of parsed info with empty data.
        """
        # Arrange
        parsed_info = {
            "intraday_steps": [],
            "intraday_heart_rate": [],
            "resting_heart_rate": None,
        }

        # Act
        intraday_steps, intraday_heart_rate, resting_heart_rate = health_utils.process_info(parsed_info)

        # Assert
        assert len(intraday_steps) == 0
        assert len(intraday_heart_rate) == 0
        assert resting_heart_rate is None

    def test_process_info_filters_zero_steps(self):
        """
        Test that process_info filters out zero step entries.
        """
        # Arrange
        parsed_info = {
            "intraday_steps": [
                {"timestamp": datetime(2024, 1, 15, 10, 30, 0), "steps": 1000, "intensity": 5, "activity_type": "running"},
                {"timestamp": datetime(2024, 1, 15, 10, 31, 0), "steps": 1000, "intensity": 6, "activity_type": "running"},  # No increase
            ],
            "intraday_heart_rate": [],
            "resting_heart_rate": None,
        }

        # Act
        intraday_steps, intraday_heart_rate, resting_heart_rate = health_utils.process_info(parsed_info)

        # Assert
        assert len(intraday_steps) == 1  # Only the first entry with positive delta
        assert len(intraday_heart_rate) == 0


class TestStoreIntradaySteps:
    """
    Test suite for store_intraday_steps function.
    """

    @patch("health.utils.health_intraday_steps_crud.create_health_intraday_steps")
    def test_store_intraday_steps_success(self, mock_create, mock_db):
        """
        Test successful storage of intraday steps.
        """
        # Arrange
        mock_step_create = health_intraday_steps_schema.HealthIntradayStepsCreate(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            steps=1000,
        )
        mock_step_model = MagicMock()
        mock_step_model.id = 1
        mock_create.return_value = [mock_step_model]

        # Act
        result = asyncio.run(
            health_utils.store_intraday_steps([mock_step_create], mock_db, 1)
        )

        # Assert
        assert result == [mock_step_model]
        mock_create.assert_called_once_with(1, [mock_step_create], mock_db)

    @patch("health.utils.health_intraday_steps_crud.create_health_intraday_steps")
    def test_store_intraday_steps_none_result(self, mock_create, mock_db):
        """
        Test error when create returns None.
        """
        # Arrange
        mock_step_create = health_intraday_steps_schema.HealthIntradayStepsCreate(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            steps=1000,
        )
        mock_create.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                health_utils.store_intraday_steps([mock_step_create], mock_db, 1)
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error creating intraday steps" in str(exc_info.value.detail)

    @patch("health.utils.health_intraday_steps_crud.create_health_intraday_steps")
    def test_store_intraday_steps_no_id(self, mock_create, mock_db):
        """
        Test error when created steps have no id.
        """
        # Arrange
        mock_step_create = health_intraday_steps_schema.HealthIntradayStepsCreate(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            steps=1000,
        )
        mock_step_model = MagicMock()
        mock_step_model.id = None
        mock_create.return_value = [mock_step_model]

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                health_utils.store_intraday_steps([mock_step_create], mock_db, 1)
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error creating intraday steps" in str(exc_info.value.detail)


class TestStoreIntradayHeartRate:
    """
    Test suite for store_intraday_heart_rate function.
    """

    @patch("health.utils.health_intraday_heart_rate_crud.create_health_intraday_heart_rate")
    def test_store_intraday_heart_rate_success(self, mock_create, mock_db):
        """
        Test successful storage of intraday heart rate.
        """
        # Arrange
        mock_heart_rate_create = health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            heart_rate=75,
        )
        mock_heart_rate_model = MagicMock()
        mock_heart_rate_model.id = 1
        mock_create.return_value = [mock_heart_rate_model]

        # Act
        result = asyncio.run(
            health_utils.store_intraday_heart_rate([mock_heart_rate_create], mock_db, 1)
        )

        # Assert
        assert result == [mock_heart_rate_model]
        mock_create.assert_called_once_with(1, [mock_heart_rate_create], mock_db)

    @patch("health.utils.health_intraday_heart_rate_crud.create_health_intraday_heart_rate")
    def test_store_intraday_heart_rate_none_result(self, mock_create, mock_db):
        """
        Test error when create returns None.
        """
        # Arrange
        mock_heart_rate_create = health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            heart_rate=75,
        )
        mock_create.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                health_utils.store_intraday_heart_rate([mock_heart_rate_create], mock_db, 1)
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error creating intraday heart_rate" in str(exc_info.value.detail)


class TestSerializeIntradaySteps:
    """
    Test suite for serialize_intraday_steps function.
    """

    @patch.dict(os.environ, {"TZ": "UTC"})
    def test_serialize_intraday_steps_success(self):
        """
        Test successful serialization of intraday steps.
        """
        # Arrange
        mock_steps = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps.timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # Act
        result = health_utils.serialize_intraday_steps(mock_steps)

        # Assert
        assert result.timestamp ==  "2024-01-15T10:30:00"


class TestSerializeIntradayHeartRate:
    """
    Test suite for serialize_intraday_heart_rate function.
    """

    @patch.dict(os.environ, {"TZ": "UTC"})
    def test_serialize_intraday_heart_rate_success(self):
        """
        Test successful serialization of intraday heart rate.
        """
        # Arrange
        mock_heart_rate = MagicMock(spec=health_intraday_heart_rate_models.HealthIntradayHeartrate)
        mock_heart_rate.timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # Act
        result = health_utils.serialize_intraday_heart_rate(mock_heart_rate)

        # Assert
        assert result.timestamp == "2024-01-15T10:30:00"
