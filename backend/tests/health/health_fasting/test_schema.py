from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


class TestHealthFastingCreateSchema:
    def test_valid_full_data(self):
        from modules.health.health_fasting.schema import HealthFastingCreate

        data = HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))
        assert data.fast_start_time is not None
        assert data.status == "in_progress"
        assert data.source == "manual"

    def test_missing_start_time(self):
        from modules.health.health_fasting.schema import HealthFastingCreate

        try:
            HealthFastingCreate()
            raise AssertionError
        except ValidationError:
            pass


class TestHealthFastingReadSchema:
    def test_valid(self):
        from modules.health.health_fasting.schema import HealthFastingRead

        data = HealthFastingRead(id=1, user_id=1)
        assert data.id == 1
        assert data.user_id == 1


class TestHealthFastingCompleteSchema:
    def test_valid(self):
        from modules.health.health_fasting.schema import FastingStatus, HealthFastingComplete

        data = HealthFastingComplete(fast_end_time=datetime(2024, 1, 15, 16, 0, 0))
        assert data.status == FastingStatus.COMPLETED.value


class TestHealthFastingStatsResponse:
    def test_valid(self):
        from modules.health.health_fasting.schema import HealthFastingStatsResponse

        data = HealthFastingStatsResponse(
            total_fasts=10,
            current_streak=3,
            longest_streak=7,
            total_fasting_seconds=864000,
            completion_rate=70.0,
        )
        assert data.total_fasts == 10


class TestEnums:
    def test_fasting_type_values(self):
        from modules.health.health_fasting.schema import FastingType

        assert FastingType.IF_16_8.value == "16:8"
        assert FastingType.OMAD.value == "OMAD"

    def test_fasting_status_values(self):
        from modules.health.health_fasting.schema import FastingStatus

        assert FastingStatus.IN_PROGRESS.value == "in_progress"
        assert FastingStatus.COMPLETED.value == "completed"


class TestCompleteStatus:
    def test_a_fast_cannot_be_completed_as_still_in_progress(self):
        from modules.health.health_fasting import schema as health_fasting_schema

        with pytest.raises(ValidationError):
            health_fasting_schema.HealthFastingComplete(
                fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC), status="in_progress"
            )

    @pytest.mark.parametrize("status", ["completed", "broken", "cancelled"])
    def test_the_ways_a_fast_can_end_are_accepted(self, status):
        from modules.health.health_fasting import schema as health_fasting_schema

        health_fasting_schema.HealthFastingComplete(
            fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC), status=status
        )
