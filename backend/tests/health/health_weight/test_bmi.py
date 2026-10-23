import pytest

import modules.health.health_weight.bmi as health_weight_bmi


class TestCalculateBmi:
    def test_calculates_weight_over_height_squared(self):
        assert health_weight_bmi.calculate_bmi(75.0, 175) == pytest.approx(75.0 / 1.75**2)

    @pytest.mark.parametrize(
        ("weight", "height"),
        [(None, 175), (75.0, None), (75.0, 0), (75.0, -10)],
    )
    def test_none_without_usable_weight_and_height(self, weight, height):
        assert health_weight_bmi.calculate_bmi(weight, height) is None
