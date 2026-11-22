from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.schema as component_schema

#: The largest price a ``Numeric(11, 2)`` column holds.
MONEY_MAX = "999999999.99"


def test_an_initial_distance_beyond_the_column_is_rejected():
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(initial_distance=1e12)


def test_an_initial_distance_at_the_column_maximum_is_accepted():
    update = gear_schema.GearUpdate(initial_distance=gear_schema.MAX_INITIAL_DISTANCE)

    assert update.initial_distance == gear_schema.MAX_INITIAL_DISTANCE


def test_the_old_initial_kilometres_field_is_refused():
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(initial_kms=10.0)


@pytest.mark.parametrize("schema", [gear_schema.GearUpdate, component_schema.GearComponentUpdate])
def test_a_purchase_value_is_a_decimal_string_with_two_decimals(schema):
    assert schema(purchase_value="129.90").purchase_value == "129.90"
    assert schema(purchase_value=MONEY_MAX).purchase_value == MONEY_MAX


@pytest.mark.parametrize("value", [129.9, 129, "129.9", "129", "129,90", "-1.00", "1000000000.00", " 12.00", "abc"])
@pytest.mark.parametrize("schema", [gear_schema.GearUpdate, component_schema.GearComponentUpdate])
def test_a_purchase_value_that_is_not_a_decimal_string_is_rejected(schema, value):
    with pytest.raises(ValidationError):
        schema(purchase_value=value)


def test_a_stored_decimal_is_read_as_a_decimal_string():
    read = component_schema.GearComponentUpdate.model_validate({"purchase_value": Decimal("45.5")})

    assert read.purchase_value == "45.50"


def test_expected_usage_beyond_the_integer_column_is_rejected():
    with pytest.raises(ValidationError):
        component_schema.GearComponentUpdate(expected_usage=2_147_483_648)


@pytest.mark.parametrize("schema", [gear_schema.GearCreateRequest, gear_schema.GearUpdate])
def test_the_acquisition_date_is_read_as_a_date(schema):
    fields = {"nickname": "Bike", "gear_type": "bike"} if schema is gear_schema.GearCreateRequest else {}

    assert schema(**fields, acquired_on="2024-03-05").acquired_on == date(2024, 3, 5)


@pytest.mark.parametrize("schema", [gear_schema.GearCreateRequest, gear_schema.GearUpdate])
def test_the_old_creation_timestamp_is_no_longer_accepted(schema):
    fields = {"nickname": "Bike", "gear_type": "bike"} if schema is gear_schema.GearCreateRequest else {}

    with pytest.raises(ValidationError):
        schema(**fields, created_at="2024-03-05T00:00:00Z")


@pytest.mark.parametrize("value", ["1899-12-31", "2999-01-01"])
def test_an_acquisition_date_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(acquired_on=value)


def test_the_acquisition_date_cannot_be_cleared():
    with pytest.raises(ValidationError):
        gear_schema.GearUpdate(acquired_on=None)
