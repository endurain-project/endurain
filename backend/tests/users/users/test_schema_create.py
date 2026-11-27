"""The administrator's create body takes a password only when the account is not invited."""

import pytest
from pydantic import ValidationError

import modules.users.users.schema as users_schema

_BODY = {"name": "New", "username": "newuser", "email": "new@example.com", "active": True, "access_type": "regular"}


def test_the_password_is_optional():
    assert users_schema.UserAdminCreate(**_BODY).password is None


def test_a_password_is_kept():
    assert users_schema.UserAdminCreate(**_BODY, password="SecurePass1!").password == "SecurePass1!"


def test_an_inactive_account_needs_a_password_because_an_invitation_cannot_activate_it():
    with pytest.raises(ValidationError) as exc:
        users_schema.UserAdminCreate(**{**_BODY, "active": False})

    assert exc.value.errors()[0]["loc"] == ("password",)


def test_an_inactive_account_with_a_password_is_accepted():
    assert users_schema.UserAdminCreate(**{**_BODY, "active": False}, password="SecurePass1!").active is False
