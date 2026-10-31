import pytest
from pydantic import ValidationError

from tests._helpers.gears import component_update


@pytest.mark.parametrize("field", ["type", "brand", "model", "purchase_date", "active"])
def test_an_update_cannot_clear_a_required_field(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        component_update(**{field: None})


def test_an_update_may_omit_required_fields_or_clear_the_retired_date():
    update = component_update(retired_date=None)

    assert "purchase_date" not in update.model_fields_set
    assert update.retired_date is None
