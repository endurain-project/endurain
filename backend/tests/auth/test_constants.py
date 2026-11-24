"""The scopes the server mints: how they are named, what each role holds and what a regular user never does."""

import re

import modules.auth.constants as auth_constants

_ADMINISTRATOR_ONLY = (
    "users:write",
    "users:read-all",
    "sessions:write",
    "api-keys:write",
    "identity-providers:read",
    "identity-providers:write",
    "server-settings:write",
    "server-settings:logs",
)


def test_every_scope_name_is_kebab_case_resource_and_action():
    """A scope is ``resource:action`` in lowercase kebab-case, or a bare resource such as ``account``."""
    name = re.compile(r"^[a-z]+(-[a-z]+)*(:[a-z]+(-[a-z]+)*)?$")

    assert [scope for scope in auth_constants.SCOPE_DICT if not name.fullmatch(scope)] == []


def test_every_scope_a_role_holds_is_described():
    assert set(auth_constants.ADMIN_ACCESS_SCOPE) == set(auth_constants.SCOPE_DICT)
    assert all(auth_constants.SCOPE_DICT[scope] for scope in auth_constants.SCOPE_DICT)


def test_an_administrator_holds_everything_a_regular_user_does():
    assert set(auth_constants.REGULAR_ACCESS_SCOPE) < set(auth_constants.ADMIN_ACCESS_SCOPE)


def test_a_regular_user_holds_no_administrator_scope():
    """Provider configuration (client ids, endpoints, mappings), other users' data and the server's settings are
    administrator-only."""
    assert [scope for scope in _ADMINISTRATOR_ONLY if scope in auth_constants.REGULAR_ACCESS_SCOPE] == []
    assert [scope for scope in _ADMINISTRATOR_ONLY if scope not in auth_constants.ADMIN_ACCESS_SCOPE] == []
