"""The administrator's edit of a user is a partial edit: every field may be left out, none may be cleared."""

import pydantic
import pytest

import modules.users.users.schema as users_schema


def test_an_admin_edit_may_leave_every_field_out():
    edit = users_schema.UserAdminEdit()

    assert edit.to_edit().model_dump(exclude_unset=True) == {}


def test_an_admin_edit_keeps_only_the_fields_it_sent():
    edit = users_schema.UserAdminEdit(access_type="admin", step_up={"current_password": "pw"})

    assert edit.to_edit().model_dump(exclude_unset=True) == {"access_type": "admin"}


@pytest.mark.parametrize("field", ["name", "username", "email", "access_type", "active"])
def test_an_admin_edit_cannot_clear_a_required_field(field):
    with pytest.raises(pydantic.ValidationError):
        users_schema.UserAdminEdit.model_validate({field: None})


def test_an_admin_edit_has_no_required_field():
    assert not [name for name, field in users_schema.UserAdminEdit.model_fields.items() if field.is_required()]
