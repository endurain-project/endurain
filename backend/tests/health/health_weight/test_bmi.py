"""The BMI arithmetic."""

import pytest

import modules.health.health_weight.bmi as health_weight_bmi
import modules.health.health_weight.schema as health_weight_schema


def test_the_bmi_is_the_weight_over_the_height_in_metres_squared():
    assert health_weight_bmi.calculate_bmi(75.0, 175) == pytest.approx(75.0 / 1.75**2)


@pytest.mark.parametrize(("weight", "height"), [(None, 175), (75.0, None), (75.0, 0), (75.0, -10)])
def test_there_is_no_bmi_without_a_usable_weight_and_height(weight, height):
    assert health_weight_bmi.calculate_bmi(weight, height) is None


@pytest.mark.parametrize(("weight", "height"), [(80.0, 70), (500.0, 100), (200.0, 1)])
def test_there_is_no_bmi_above_the_largest_a_record_may_carry(weight, height):
    assert health_weight_bmi.calculate_bmi(weight, height) is None


def test_the_largest_bmi_is_usable_and_one_above_it_is_not():
    top = health_weight_schema.MAX_BMI

    assert health_weight_bmi.calculate_bmi(float(top), 100) == pytest.approx(top)
    assert health_weight_bmi.calculate_bmi(top + 0.1, 100) is None


def test_there_is_no_bmi_for_a_negative_weight():
    assert health_weight_bmi.calculate_bmi(-5.0, 175) is None
