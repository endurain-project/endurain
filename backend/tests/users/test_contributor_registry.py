"""Tests for the users contributor registry."""

from unittest.mock import MagicMock

import pytest

import modules.users.contributor_registry as users_contributor_registry
import modules.users.contributors as users_contributors
import modules.users.users_profile.contracts as users_profile_contracts


@pytest.fixture(autouse=True)
def _restore_registry():
    previous = (
        users_contributor_registry._erasers,
        users_contributor_registry._lifecycle_hooks,
        users_contributor_registry._profile_readers,
        dict(users_contributor_registry._profile_sections),
    )
    users_contributor_registry.clear()
    yield
    (
        users_contributor_registry._erasers,
        users_contributor_registry._lifecycle_hooks,
        users_contributor_registry._profile_readers,
        sections,
    ) = previous
    users_contributor_registry._profile_sections.update(sections)


def test_an_uninstalled_registry_fails_loudly():
    with pytest.raises(RuntimeError):
        users_contributor_registry.erasers()


def test_installed_erasers_are_returned():
    erasers = users_contributors.UserErasers(
        delete_activities=MagicMock(), delete_staged_files=MagicMock(), delete_bulk_import_errors=MagicMock()
    )

    users_contributor_registry.register(erasers)

    assert users_contributor_registry.erasers() is erasers


def test_an_uninstalled_registry_names_the_composition_call():
    for read in (
        users_contributor_registry.erasers,
        users_contributor_registry.lifecycle_hooks,
        users_contributor_registry.profile_readers,
    ):
        with pytest.raises(RuntimeError, match=r"module_registry\.configure_user_contributors\(\)"):
            read()


def test_installed_lifecycle_hooks_are_returned():
    hooks = users_contributors.UserLifecycleHooks(stage_new_user=MagicMock(), stage_height_change=MagicMock())

    users_contributor_registry.register_lifecycle_hooks(hooks)

    assert users_contributor_registry.lifecycle_hooks() is hooks


def test_installed_profile_readers_are_returned():
    readers = users_contributors.ProfileReaders(follow_counts=MagicMock())

    users_contributor_registry.register_profile_readers(readers)

    assert users_contributor_registry.profile_readers() is readers


def test_clear_removes_every_installed_callback():
    users_contributor_registry.register_lifecycle_hooks(
        users_contributors.UserLifecycleHooks(stage_new_user=MagicMock(), stage_height_change=MagicMock())
    )
    users_contributor_registry.register_profile_readers(users_contributors.ProfileReaders(follow_counts=MagicMock()))

    users_contributor_registry.clear()

    with pytest.raises(RuntimeError):
        users_contributor_registry.lifecycle_hooks()
    with pytest.raises(RuntimeError):
        users_contributor_registry.profile_readers()


def _section(key: str) -> users_profile_contracts.ProfileRecordsSection:
    return users_profile_contracts.ProfileRecordsSection(
        key=key, export=lambda user_id, db: [], restore=lambda records, user_id, ids, db: 0
    )


def test_profile_sections_are_returned_in_registration_order():
    first, second, third = _section("b"), _section("a"), _section("c")
    for section in (first, second, third):
        users_contributor_registry.register_profile_section(section)

    assert users_contributor_registry.profile_sections() == (first, second, third)


def test_a_profile_section_key_cannot_be_registered_twice():
    users_contributor_registry.register_profile_section(_section("gears"))

    with pytest.raises(ValueError, match="gears"):
        users_contributor_registry.register_profile_section(_section("gears"))


def test_no_installed_profile_sections_fail_loudly():
    with pytest.raises(RuntimeError, match="configure_user_contributors"):
        users_contributor_registry.profile_sections()


def test_clear_removes_the_profile_sections():
    users_contributor_registry.register_profile_section(_section("gears"))

    users_contributor_registry.clear()

    with pytest.raises(RuntimeError):
        users_contributor_registry.profile_sections()
