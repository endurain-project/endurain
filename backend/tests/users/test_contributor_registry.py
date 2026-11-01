"""Tests for the users erasers registry."""

from unittest.mock import MagicMock

import pytest

import modules.users.contributor_registry as users_contributor_registry
import modules.users.contributors as users_contributors


@pytest.fixture(autouse=True)
def _restore_registry():
    previous = users_contributor_registry._erasers
    users_contributor_registry.clear()
    yield
    users_contributor_registry._erasers = previous


def test_an_uninstalled_registry_fails_loudly():
    with pytest.raises(RuntimeError):
        users_contributor_registry.erasers()


def test_installed_erasers_are_returned():
    erasers = users_contributors.UserErasers(delete_activities=MagicMock(), delete_staged_files=MagicMock())

    users_contributor_registry.register(erasers)

    assert users_contributor_registry.erasers() is erasers
