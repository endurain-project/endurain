from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


class TestHealthFastingCreateSchema:
    def test_a_session_without_a_status_is_in_progress_and_a_client_cannot_set_the_source(self):
        from modules.health.health_fasting.schema import HealthFastingCreate

        data = HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC))
        assert data.fast_start_time is not None
        assert data.status == "in_progress"
        assert not hasattr(data, "source")

    def test_an_imported_session_without_a_source_is_manual(self):
        from modules.health.health_fasting.schema import HealthFastingImport

        data = HealthFastingImport(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))
        assert data.source == "manual"

    def test_an_import_reads_a_missing_offset_as_utc(self):
        from modules.health.health_fasting.schema import HealthFastingImport

        data = HealthFastingImport(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))
        assert data.fast_start_time == datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)

    def test_a_request_without_an_offset_is_refused(self):
        import pytest
        from pydantic import ValidationError

        from modules.health.health_fasting.schema import HealthFastingComplete, HealthFastingCreate

        with pytest.raises(ValidationError):
            HealthFastingCreate(fast_start_time="2024-01-15T08:00:00")
        with pytest.raises(ValidationError):
            HealthFastingComplete(fast_end_time="2024-01-16T08:00:00")

    def test_the_end_of_a_completed_fast_is_bounded(self):
        import pytest
        from pydantic import ValidationError

        from modules.health.health_fasting.schema import HealthFastingComplete

        with pytest.raises(ValidationError):
            HealthFastingComplete(fast_end_time="3000-01-01T00:00:00Z")
        with pytest.raises(ValidationError):
            HealthFastingComplete(fast_end_time="1800-01-01T00:00:00Z")

    def test_missing_start_time(self):
        from modules.health.health_fasting.schema import HealthFastingCreate

        try:
            HealthFastingCreate()
            raise AssertionError
        except ValidationError:
            pass


class TestHealthFastingCompleteSchema:
    def test_a_completion_without_a_status_is_completed(self):
        from modules.health.health_fasting.schema import FastingStatus, HealthFastingComplete

        data = HealthFastingComplete(fast_end_time=datetime(2024, 1, 15, 16, 0, 0, tzinfo=UTC))
        assert data.status == FastingStatus.COMPLETED.value


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
