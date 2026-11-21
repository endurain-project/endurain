import uuid

import pytest
from pydantic import ValidationError

import modules.gears.gear_components.schema as schema
from tests._factories.gears import component_payload


@pytest.mark.parametrize("field", ["type", "brand", "model", "purchase_date", "active"])
def test_an_update_cannot_clear_a_required_field(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        schema.GearComponentUpdate(**{field: None})


def test_an_update_may_omit_required_fields_or_clear_the_retired_date():
    update = schema.GearComponentUpdate(retired_date=None)

    assert "purchase_date" not in update.model_fields_set
    assert update.retired_date is None


def test_a_create_rejects_a_gear_id_that_is_not_a_uuid():
    with pytest.raises(ValidationError):
        component_payload("not-a-uuid")


def test_a_create_rejects_an_integer_gear_id():
    with pytest.raises(ValidationError):
        component_payload(1)


def test_a_create_accepts_a_uuid_gear_id():
    gear_id = uuid.uuid4()

    assert component_payload(gear_id).gear_id == gear_id
