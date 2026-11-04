"""Request schemas refuse a blank name and one carrying direction controls; stored names still read."""

import pytest
from pydantic import ValidationError

import modules.users.users.schema as users_schema

_SIGNUP = {"username": "newuser", "email": "new@example.com", "password": "SecurePass1!"}
_ADMIN = {
    "username": "newuser",
    "email": "new@example.com",
    "password": "SecurePass1!",
    "access_type": "regular",
    "active": True,
}
_FIRST_ADMIN = {"username": "newuser", "email": "new@example.com", "password": "SecurePass1!"}
_BAD_NAMES = [" ", "\t\n", chr(0xA0), "Eve‮evil", "a‎b", "a‏b", "a؜b", "a⁦b", "a⁩b", "a﻿b", "a⁠b"]
_GOOD_NAMES = ["Ana María", "می‌خواهم", "क्‍ष", "👨‍👩‍👧", " padded name "]


def _validators():
    return {
        "signup": lambda name: users_schema.UsersSignup(name=name, **_SIGNUP),
        "admin_create": lambda name: users_schema.UsersCreate(name=name, **_ADMIN),
        "first_admin": lambda name: users_schema.FirstAdminCreate(name=name, **_FIRST_ADMIN),
        "admin_edit": lambda name: users_schema.UsersEdit(
            name=name, username="newuser", email="new@example.com", access_type="regular", active=True
        ),
        "profile_update": lambda name: users_schema.ProfileUpdate(name=name),
    }


@pytest.mark.parametrize("shape", list(_validators()))
@pytest.mark.parametrize("name", _BAD_NAMES)
def test_a_blank_or_directional_name_is_refused(shape, name):
    with pytest.raises(ValidationError):
        _validators()[shape](name)


@pytest.mark.parametrize("shape", list(_validators()))
@pytest.mark.parametrize("name", _GOOD_NAMES)
def test_joiners_and_inner_spaces_are_accepted(shape, name):
    assert _validators()[shape](name).name == name


def test_a_stored_name_still_reads():
    stored = {
        "id": 1,
        "username": "olduser",
        "email": "old@example.com",
        "access_type": "regular",
        "active": True,
    }
    for name in (" ", "Eve‮evil"):
        read = users_schema.UsersRead(name=name, **stored)
        assert read.name == name
        assert users_schema.UsersEdit.from_read(read).name == name
