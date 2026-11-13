import pytest

import modules.health.health_weight.bmi as health_weight_bmi
import modules.health.health_weight.schema as health_weight_schema


class TestCalculateBmi:
    def test_calculates_weight_over_height_squared(self):
        assert health_weight_bmi.calculate_bmi(75.0, 175) == pytest.approx(75.0 / 1.75**2)

    @pytest.mark.parametrize(
        ("weight", "height"),
        [(None, 175), (75.0, None), (75.0, 0), (75.0, -10)],
    )
    def test_none_without_usable_weight_and_height(self, weight, height):
        assert health_weight_bmi.calculate_bmi(weight, height) is None

    @pytest.mark.parametrize(("weight", "height"), [(80.0, 70), (500.0, 100), (200.0, 1)])
    def test_none_when_the_result_exceeds_the_schema_bound(self, weight, height):
        assert health_weight_bmi.calculate_bmi(weight, height) is None

    def test_none_for_a_negative_weight(self):
        assert health_weight_bmi.calculate_bmi(-5.0, 175) is None

    def test_the_bound_itself_is_usable(self):
        assert health_weight_bmi.calculate_bmi(100.0, 100) == pytest.approx(100.0)

    def test_the_bound_is_the_schemas(self):
        assert health_weight_schema.HealthWeightBase.model_fields["bmi"].metadata[1].le == health_weight_schema.MAX_BMI
