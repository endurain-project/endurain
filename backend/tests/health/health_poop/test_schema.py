from datetime import UTC, datetime

from pydantic import ValidationError


class TestHealthPoopCreateSchema:
    def test_valid(self):
        from modules.health.health_poop.schema import HealthPoopCreate

        data = HealthPoopCreate(date_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        assert data.date_time is not None
        assert not hasattr(data, "source")

    def test_an_imported_record_without_a_source_is_manual(self):
        from modules.health.health_poop.schema import HealthPoopImport

        data = HealthPoopImport(date_time=datetime(2024, 1, 15, 10, 0, 0))
        assert data.source == "manual"
        assert data.date_time == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_a_request_without_an_offset_is_refused(self):
        import pytest
        from pydantic import ValidationError

        from modules.health.health_poop.schema import HealthPoopCreate

        with pytest.raises(ValidationError):
            HealthPoopCreate(date_time="2024-01-15T10:00:00")

    def test_missing_date_time(self):
        from modules.health.health_poop.schema import HealthPoopCreate

        try:
            HealthPoopCreate()
            raise AssertionError
        except ValidationError:
            pass


class TestEnums:
    def test_bristol_type(self):
        from modules.health.health_poop.schema import BristolType

        assert BristolType.TYPE_1.value == "type_1"
        assert BristolType.TYPE_1.stored == 1
        assert BristolType.TYPE_7.stored == 7
