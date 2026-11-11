from datetime import UTC, datetime
from datetime import date as datetime_date

import pytest
from pydantic import ValidationError

import modules.health.health_sleep.schema as health_sleep_schema


class TestHealthSleepSchema:
    """
    Test suite for HealthSleep Pydantic schema.
    """

    def test_health_sleep_valid_full_data(self):
        """
        Test HealthSleepRead schema with all valid fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepRead(
            updated_at="2024-01-01T00:00:00Z",
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            sleep_start_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            sleep_end_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
            total_sleep_seconds=28800,
            deep_sleep_seconds=7200,
            light_sleep_seconds=14400,
            rem_sleep_seconds=7200,
            avg_heart_rate=55,
            min_heart_rate=45,
            max_heart_rate=75,
            sleep_score_overall=85,
            source=health_sleep_schema.Source.GARMIN,
        )

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.user_id == 1
        assert health_sleep.date == datetime_date(2024, 1, 15)
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.sleep_score_overall == 85
        assert health_sleep.source == "garmin"

    def test_health_sleep_minimal_data(self):
        """
        Test HealthSleepBase schema with minimal required fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase()

        # Assert
        assert health_sleep.date is None
        assert health_sleep.total_sleep_seconds is None

    def test_health_sleep_with_none_values(self):
        """
        Test HealthSleepRead schema allows None for optional fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepRead(
            updated_at="2024-01-01T00:00:00Z",
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
            deep_sleep_seconds=None,
            avg_heart_rate=None,
        )

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.deep_sleep_seconds is None
        assert health_sleep.avg_heart_rate is None

    def test_health_sleep_forbid_extra_fields(self):
        """
        Test that HealthSleepBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(total_sleep_seconds=28800, extra_field="not allowed")

        assert "extra_field" in str(exc_info.value)

    def test_health_sleep_from_attributes(self):
        """
        Test HealthSleepRead schema can be created from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            updated_at = "2024-01-01T00:00:00Z"
            date = datetime_date(2024, 1, 15)
            sleep_start_time_gmt = datetime(2024, 1, 14, 22, 0, 0)
            sleep_end_time_gmt = datetime(2024, 1, 15, 6, 0, 0)
            sleep_start_time_local = None
            sleep_end_time_local = None
            total_sleep_seconds = 28800
            nap_time_seconds = None
            unmeasurable_sleep_seconds = None
            deep_sleep_seconds = 7200
            light_sleep_seconds = 14400
            rem_sleep_seconds = 7200
            awake_sleep_seconds = 0
            avg_heart_rate = 55
            min_heart_rate = 45
            max_heart_rate = 75
            avg_spo2_percent = 97
            lowest_spo2_percent = 95
            highest_spo2_percent = 99
            avg_respiration = None
            lowest_respiration = None
            highest_respiration = None
            avg_stress_level = None
            awake_count = 2
            restless_moments_count = 5
            sleep_score_overall = 85
            sleep_score_duration = "GOOD"
            sleep_score_quality = "GOOD"
            garminconnect_sleep_id = None
            sleep_stages = None
            source = "garmin"
            hrv_status = None
            resting_heart_rate = 50
            avg_skin_temp_deviation = None
            awake_count_score = None
            rem_percentage_score = None
            deep_percentage_score = None
            light_percentage_score = None
            avg_sleep_stress = None
            sleep_stress_score = None

        # Act
        health_sleep = health_sleep_schema.HealthSleepRead.model_validate(MockORMModel())

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.source == "garmin"

    def test_health_sleep_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        health_sleep = health_sleep_schema.HealthSleepBase(total_sleep_seconds=28800)

        # Act
        health_sleep.total_sleep_seconds = 32400
        health_sleep.sleep_score_overall = 90

        # Assert
        assert health_sleep.total_sleep_seconds == 32400
        assert health_sleep.sleep_score_overall == 90

    def test_health_sleep_heart_rate_validation_valid(self):
        """
        Test heart rate validation with valid values.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            avg_heart_rate=60,
            min_heart_rate=45,
            max_heart_rate=85,
        )

        # Assert
        assert health_sleep.avg_heart_rate == 60
        assert health_sleep.min_heart_rate == 45
        assert health_sleep.max_heart_rate == 85

    def test_health_sleep_heart_rate_validation_invalid_low(self):
        """
        Test heart rate validation rejects values below 20 bpm.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(min_heart_rate=15)

        assert "greater than or equal to 20" in str(exc_info.value)

    def test_health_sleep_heart_rate_validation_invalid_high(self):
        """
        Test heart rate validation rejects values above 220 bpm.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(max_heart_rate=250)

        assert "less than or equal to 220" in str(exc_info.value)

    def test_health_sleep_spo2_validation_valid(self):
        """
        Test SpO2 validation with valid values.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            avg_spo2_percent=97,
            lowest_spo2_percent=95,
            highest_spo2_percent=99,
        )

        # Assert
        assert health_sleep.avg_spo2_percent == 97
        assert health_sleep.lowest_spo2_percent == 95
        assert health_sleep.highest_spo2_percent == 99

    def test_health_sleep_spo2_validation_invalid_low(self):
        """
        Test SpO2 validation rejects values below 70%.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(lowest_spo2_percent=65)

        assert "greater than or equal to 70" in str(exc_info.value)

    def test_health_sleep_spo2_validation_invalid_high(self):
        """
        Test SpO2 validation rejects values above 100%.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(highest_spo2_percent=105)

        assert "less than or equal to 100" in str(exc_info.value)

    def test_health_sleep_time_validation_valid(self):
        """
        Test sleep time validation with valid start < end times.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            sleep_start_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            sleep_end_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
        )

        # Assert
        assert health_sleep.sleep_start_time_gmt < health_sleep.sleep_end_time_gmt

    def test_health_sleep_time_validation_invalid(self):
        """
        Test sleep time validation rejects start >= end times.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(
                sleep_start_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
                sleep_end_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            )

        assert "before" in str(exc_info.value)


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_sleep_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthSleepRead schema.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepRead(
            updated_at="2024-01-01T00:00:00Z", id=1, user_id=1, source=health_sleep_schema.Source.GARMIN
        )

        # Assert
        assert health_sleep.source == "garmin"


class TestSleepScoreEnum:
    """
    Test suite for SleepScore enum.
    """

    def test_sleep_score_enum_values(self):
        """
        Test SleepScore enum has all expected values.
        """
        # Assert
        assert health_sleep_schema.SleepScore.EXCELLENT.value == "EXCELLENT"
        assert health_sleep_schema.SleepScore.GOOD.value == "GOOD"
        assert health_sleep_schema.SleepScore.FAIR.value == "FAIR"
        assert health_sleep_schema.SleepScore.POOR.value == "POOR"


class TestHRVStatusEnum:
    """
    Test suite for HRVStatus enum.
    """

    def test_hrv_status_enum_values(self):
        """
        Test HRVStatus enum has all expected values.
        """
        # Assert
        assert health_sleep_schema.HRVStatus.BALANCED.value == "BALANCED"
        assert health_sleep_schema.HRVStatus.UNBALANCED.value == "UNBALANCED"
        assert health_sleep_schema.HRVStatus.LOW.value == "LOW"
        assert health_sleep_schema.HRVStatus.POOR.value == "POOR"


class TestSleepTimeOrdering:
    """The start must precede the end, whether the times carry an offset or not."""

    _AWARE_START = datetime(2026, 1, 1, 22, tzinfo=UTC)
    _AWARE_END = datetime(2026, 1, 2, 6, tzinfo=UTC)
    _NAIVE_START = datetime(2026, 1, 1, 22)
    _NAIVE_END = datetime(2026, 1, 2, 6)

    @pytest.mark.parametrize("aware_first", [True, False])
    def test_a_mixed_wall_clock_pair_in_order_is_accepted(self, aware_first):
        start, end = (self._AWARE_START, self._NAIVE_END) if aware_first else (self._NAIVE_START, self._AWARE_END)

        health_sleep_schema.HealthSleepCreate(sleep_start_time_local=start, sleep_end_time_local=end)

    def test_an_instant_without_an_offset_is_refused(self):
        with pytest.raises(ValidationError):
            health_sleep_schema.HealthSleepCreate(sleep_start_time_gmt=self._NAIVE_START)

    def test_an_import_reads_a_missing_offset_as_utc(self):
        record = health_sleep_schema.HealthSleepImport(sleep_start_time_gmt=self._NAIVE_START)

        assert record.sleep_start_time_gmt == self._AWARE_START

    @pytest.mark.parametrize("pair", ["gmt", "local"])
    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (_AWARE_END, _NAIVE_START),
            (_NAIVE_END, _AWARE_START),
            (_AWARE_START, _NAIVE_START),
            (_NAIVE_START, _AWARE_START),
        ],
        ids=["aware-after-naive", "naive-after-aware", "aware-equals-naive", "naive-equals-aware"],
    )
    def test_a_mixed_pair_not_in_order_is_a_validation_error(self, pair, start, end):
        with pytest.raises(ValidationError):
            health_sleep_schema.HealthSleepCreate(**{f"sleep_start_time_{pair}": start, f"sleep_end_time_{pair}": end})


class TestHealthSleepListItem:
    def test_the_flag_is_derived_from_a_rows_stages(self):
        class Row:
            id = 1
            user_id = 1
            updated_at = "2024-01-01T00:00:00Z"

            def __init__(self, sleep_stages):
                self.sleep_stages = sleep_stages

        assert (
            health_sleep_schema.HealthSleepListItem.model_validate(
                Row([{"stage_type": "deep", "duration_seconds": 60}])
            ).has_sleep_stages
            is True
        )
        assert health_sleep_schema.HealthSleepListItem.model_validate(Row(None)).has_sleep_stages is False
        assert health_sleep_schema.HealthSleepListItem.model_validate(Row([])).has_sleep_stages is False

    def test_it_carries_no_stages_and_forbids_them_as_a_field(self):
        item = health_sleep_schema.HealthSleepListItem(
            updated_at="2024-01-01T00:00:00Z", id=1, user_id=1, has_sleep_stages=True
        )

        assert "sleep_stages" not in item.model_dump()
        assert "sleep_stages" not in health_sleep_schema.HealthSleepListItem.model_json_schema()["properties"]

    def test_it_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            health_sleep_schema.HealthSleepListItem(
                updated_at="2024-01-01T00:00:00Z", id=1, user_id=1, has_sleep_stages=False, extra_field=1
            )

    def test_it_has_every_read_field_but_the_stages(self):
        read = set(health_sleep_schema.HealthSleepRead.model_fields)
        item = set(health_sleep_schema.HealthSleepListItem.model_fields)

        assert item == (read - {"sleep_stages"}) | {"has_sleep_stages"}
