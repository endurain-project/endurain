from datetime import datetime

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
        assert data.status == FastingStatus.COMPLETED


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
