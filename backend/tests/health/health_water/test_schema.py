import uuid
from datetime import date

_ID = uuid.uuid4()
_OTHER_ID = uuid.uuid4()


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


class TestHealthWaterCreateSchema:
    def test_valid(self):
        from modules.health.health_water.schema import HealthWaterCreate

        data = HealthWaterCreate(amount_ml=500.0)
        assert data.amount_ml == 500.0
        assert data.date is None

    def test_with_date(self):
        from modules.health.health_water.schema import HealthWaterCreate

        data = HealthWaterCreate(amount_ml=1000.0, date=date(2024, 1, 15))
        assert data.date == date(2024, 1, 15)


class TestHealthWaterReadSchema:
    def test_valid(self):
        from modules.health.health_water.schema import HealthWaterRead

        data = HealthWaterRead(updated_at="2024-01-01T00:00:00Z", id=_ID, user_id=_USER_ID, amount_ml=500.0)
        assert data.id == _ID
        assert data.amount_ml == 500.0


class TestEnums:
    def test_source_values(self):
        from modules.health.health_water.schema import Source

        assert Source.MANUAL.value == "manual"
        assert Source.GARMIN.value == "garmin"
