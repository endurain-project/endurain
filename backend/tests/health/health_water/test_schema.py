from datetime import date


class TestHealthWaterCreateSchema:
    def test_valid(self):
        from modules.health.health_water.schema import HealthWaterCreate

        data = HealthWaterCreate(amount_ml=500.0)
        assert data.amount_ml == 500.0
        assert data.date is not None

    def test_with_date(self):
        from modules.health.health_water.schema import HealthWaterCreate

        data = HealthWaterCreate(amount_ml=1000.0, date=date(2024, 1, 15))
        assert data.date == date(2024, 1, 15)


class TestHealthWaterReadSchema:
    def test_valid(self):
        from modules.health.health_water.schema import HealthWaterRead

        data = HealthWaterRead(id=1, user_id=1, amount_ml=500.0)
        assert data.id == 1
        assert data.amount_ml == 500.0


class TestEnums:
    def test_source_values(self):
        from modules.health.health_water.schema import Source

        assert Source.MANUAL.value == "manual"
        assert Source.GARMIN.value == "garmin"
