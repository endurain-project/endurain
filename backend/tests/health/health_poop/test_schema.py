from datetime import datetime

from pydantic import ValidationError


class TestHealthPoopCreateSchema:
    def test_valid(self):
        from modules.health.health_poop.schema import HealthPoopCreate

        data = HealthPoopCreate(date_time=datetime(2024, 1, 15, 10, 0, 0))
        assert data.date_time is not None
        assert data.source == "manual"

    def test_missing_date_time(self):
        from modules.health.health_poop.schema import HealthPoopCreate

        try:
            HealthPoopCreate()
            raise AssertionError
        except ValidationError:
            pass


class TestHealthPoopReadSchema:
    def test_valid(self):
        from modules.health.health_poop.schema import HealthPoopRead

        data = HealthPoopRead(id=1, user_id=1)
        assert data.id == 1
        assert data.user_id == 1


class TestEnums:
    def test_bristol_type(self):
        from modules.health.health_poop.schema import BristolType

        assert BristolType.TYPE_1.value == 1
        assert BristolType.TYPE_7.value == 7

    def test_color_values(self):
        from modules.health.health_poop.schema import Color

        assert Color.BROWN.value == "brown"
        assert Color.GREEN.value == "green"
