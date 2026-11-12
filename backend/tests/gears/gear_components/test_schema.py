import uuid

import pytest
from pydantic import ValidationError

from tests._helpers.gears import component_create, component_update


@pytest.mark.parametrize("field", ["type", "brand", "model", "purchase_date", "active"])
def test_an_update_cannot_clear_a_required_field(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        component_update(**{field: None})


def test_an_update_may_omit_required_fields_or_clear_the_retired_date():
    update = component_update(retired_date=None)

    assert "purchase_date" not in update.model_fields_set
    assert update.retired_date is None


def test_a_create_rejects_a_gear_id_that_is_not_a_uuid():
    with pytest.raises(ValidationError):
        component_create("not-a-uuid")


def test_a_create_rejects_an_integer_gear_id():
    with pytest.raises(ValidationError):
        component_create(1)


def test_a_create_accepts_a_uuid_gear_id():
    gear_id = uuid.uuid4()

    assert component_create(gear_id).gear_id == gear_id
