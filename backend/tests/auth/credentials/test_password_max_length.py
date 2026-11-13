"""Every request that carries a password bounds it by the one credentials maximum."""

import pytest
from pydantic import ValidationError

import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.schema as authentication_schema
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.password_reset_tokens.schema as reset_schema
import modules.auth.schema as step_up_schema
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.users.users.schema as users_schema

_STEP_UP = {"current_password": "x"}
_TOKEN = "t" * 43

_NEW_PASSWORD_SHAPES = [
    pytest.param(reset_schema.PasswordResetConfirm, {"token": _TOKEN}, id="reset-confirm"),
    pytest.param(
        authentication_schema.PasswordChangeLoginRequest,
        {"password_change_challenge": "c" * 43},
        id="sign-in-password-change",
    ),
    pytest.param(sign_up_schema.SignUpConfirm, {"token": _TOKEN}, id="sign-up-confirm"),
    pytest.param(users_schema.UserSignup, {"name": "Bob", "username": "bob", "email": "bob@example.com"}, id="sign-up"),
    pytest.param(users_schema.UserEditPassword, {"step_up": _STEP_UP}, id="profile-change"),
    pytest.param(users_schema.UserAdminEditPassword, {"step_up": _STEP_UP}, id="admin-set"),
    pytest.param(
        users_schema.UserAdminCreate,
        {"name": "Bob", "username": "bob", "email": "bob@example.com", "access_type": "regular", "active": True},
        id="admin-create",
    ),
]


def test_the_maximum_is_256():
    assert credentials_contracts.PASSWORD_MAX_LENGTH == 256


@pytest.mark.parametrize(("schema", "fields"), _NEW_PASSWORD_SHAPES)
def test_a_new_password_of_the_maximum_length_is_accepted(schema, fields):
    schema(**fields, password="a" * credentials_contracts.PASSWORD_MAX_LENGTH)


@pytest.mark.parametrize(("schema", "fields"), _NEW_PASSWORD_SHAPES)
def test_a_short_new_password_reaches_the_password_policy(schema, fields):
    """The schema sets no minimum, so the policy answers a short password with ``password-too-short``."""
    assert schema(**fields, password="short").password == "short"


@pytest.mark.parametrize(("schema", "fields"), _NEW_PASSWORD_SHAPES)
def test_a_new_password_over_the_maximum_is_refused(schema, fields):
    with pytest.raises(ValidationError):
        schema(**fields, password="a" * (credentials_contracts.PASSWORD_MAX_LENGTH + 1))


def test_a_current_password_of_the_maximum_length_is_accepted():
    step_up_schema.StepUpVerification(current_password="a" * credentials_contracts.PASSWORD_MAX_LENGTH)


def test_a_current_password_over_the_maximum_is_refused():
    with pytest.raises(ValidationError):
        step_up_schema.StepUpVerification(current_password="a" * (credentials_contracts.PASSWORD_MAX_LENGTH + 1))


def test_a_password_set_through_reset_passes_as_a_step_up_current_password():
    reset = reset_schema.PasswordResetConfirm(token=_TOKEN, password="a" * 256)

    step_up_schema.StepUpVerification(current_password=reset.password)


def test_the_login_form_bounds_the_password_by_the_same_maximum():
    assert authentication_dependencies.LOGIN_FIELD_MAX_LENGTH == credentials_contracts.PASSWORD_MAX_LENGTH
