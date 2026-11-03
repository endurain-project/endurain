"""``NotClearable`` refuses an explicit null for the fields an edit lists."""

import pytest
from pydantic import ConfigDict, ValidationError

import core.partial_update as core_partial_update


class Edit(core_partial_update.NotClearable):
    not_clearable = ("name", "age")

    name: str | None = None
    age: int | None = None
    note: str | None = None


def test_a_listed_field_may_be_omitted():
    assert Edit(note="x").model_fields_set == {"note"}


def test_a_listed_field_may_be_set():
    assert Edit(name="Ana").name == "Ana"


@pytest.mark.parametrize("field", ["name", "age"])
def test_a_listed_field_cannot_be_cleared(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        Edit(**{field: None})


def test_every_cleared_field_is_named():
    with pytest.raises(ValidationError, match="name, age cannot be null"):
        Edit(name=None, age=None)


def test_an_unlisted_field_can_still_be_cleared():
    assert Edit(note=None).model_fields_set == {"note"}


def test_assignment_validation_refuses_clearing_too():
    class Validated(Edit):
        model_config = ConfigDict(validate_assignment=True)

    edit = Validated(name="Ana")

    with pytest.raises(ValidationError, match="name cannot be null"):
        edit.name = None
