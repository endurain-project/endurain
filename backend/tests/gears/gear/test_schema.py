import pytest
from pydantic import ValidationError

import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.schema as component_schema

#: The largest value a ``Numeric(11, 2)`` column holds.
NUMERIC_11_2_MAX = 999_999_999.99


@pytest.mark.parametrize("field", ["initial_kms", "purchase_value"])
def test_a_gear_amount_beyond_the_column_is_rejected(field):
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(**{field: 1e9})


@pytest.mark.parametrize("field", ["initial_kms", "purchase_value"])
def test_a_gear_amount_at_the_column_maximum_is_accepted(field):
    assert getattr(gear_schema.GearUpdate(**{field: NUMERIC_11_2_MAX}), field) == NUMERIC_11_2_MAX


def test_a_component_purchase_value_beyond_the_column_is_rejected():
    with pytest.raises(ValidationError):
        component_schema.GearComponentUpdate(purchase_value=1e9)


def test_a_component_purchase_value_at_the_column_maximum_is_accepted():
    update = component_schema.GearComponentUpdate(purchase_value=NUMERIC_11_2_MAX)

    assert update.purchase_value == NUMERIC_11_2_MAX


def test_expected_kms_beyond_the_integer_column_is_rejected():
    with pytest.raises(ValidationError):
        component_schema.GearComponentUpdate(expected_kms=2_147_483_648)
