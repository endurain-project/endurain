"""The users contributor registry: what composition installs for the users namespace, and its failures."""

import pytest

import module_registry
import modules.users.contributor_registry as users_contributor_registry
import modules.users.contributors as users_contributors
import modules.users.users_profile.contracts as users_profile_contracts


@pytest.fixture(autouse=True)
def _empty_registry():
    users_contributor_registry.clear()
    yield
    users_contributor_registry.clear()


def _noop(*_args) -> int:
    return 0


def _erasers() -> users_contributors.UserErasers:
    return users_contributors.UserErasers(
        delete_activities=_noop, delete_notifications=_noop, delete_staged_files=_noop, delete_bulk_import_errors=_noop
    )


def _hooks() -> users_contributors.UserLifecycleHooks:
    return users_contributors.UserLifecycleHooks(stage_new_user=_noop, stage_height_change=_noop)


def _readers() -> users_contributors.ProfileReaders:
    return users_contributors.ProfileReaders(follow_counts=_noop)


def _section(key: str) -> users_profile_contracts.ProfileRecordsSection:
    return users_profile_contracts.ProfileRecordsSection(
        key=key, export=lambda user_id, db: [], restore=lambda records, user_id, ids, db: 0
    )


class TestUninstalled:
    @pytest.mark.parametrize(
        "read",
        [
            users_contributor_registry.erasers,
            users_contributor_registry.lifecycle_hooks,
            users_contributor_registry.profile_readers,
            users_contributor_registry.profile_sections,
        ],
        ids=["erasers", "lifecycle_hooks", "profile_readers", "profile_sections"],
    )
    def test_reading_what_composition_never_installed_fails_naming_the_call_that_installs_it(self, read):
        with pytest.raises(RuntimeError, match=r"module_registry\.configure_user_contributors\(\)"):
            read()


class TestInstalled:
    def test_installed_erasers_are_returned(self):
        erasers = _erasers()

        users_contributor_registry.register(erasers)

        assert users_contributor_registry.erasers() is erasers

    def test_installed_lifecycle_hooks_are_returned(self):
        hooks = _hooks()

        users_contributor_registry.register_lifecycle_hooks(hooks)

        assert users_contributor_registry.lifecycle_hooks() is hooks

    def test_installed_profile_readers_are_returned(self):
        readers = _readers()

        users_contributor_registry.register_profile_readers(readers)

        assert users_contributor_registry.profile_readers() is readers

    def test_a_second_installation_replaces_the_first(self):
        users_contributor_registry.register(_erasers())
        replacement = _erasers()

        users_contributor_registry.register(replacement)

        assert users_contributor_registry.erasers() is replacement

    def test_clearing_removes_every_installed_callback_and_section(self):
        users_contributor_registry.register(_erasers())
        users_contributor_registry.register_lifecycle_hooks(_hooks())
        users_contributor_registry.register_profile_readers(_readers())
        users_contributor_registry.register_profile_section(_section("gears"))

        users_contributor_registry.clear()

        for read in (
            users_contributor_registry.erasers,
            users_contributor_registry.lifecycle_hooks,
            users_contributor_registry.profile_readers,
            users_contributor_registry.profile_sections,
        ):
            with pytest.raises(RuntimeError):
                read()


class TestProfileSections:
    def test_sections_are_returned_in_registration_order(self):
        first, second, third = _section("b"), _section("a"), _section("c")
        for section in (first, second, third):
            users_contributor_registry.register_profile_section(section)

        assert users_contributor_registry.profile_sections() == (first, second, third)

    def test_a_section_key_cannot_be_registered_twice(self):
        users_contributor_registry.register_profile_section(_section("gears"))

        with pytest.raises(ValueError, match="gears"):
            users_contributor_registry.register_profile_section(_section("gears"))

        assert len(users_contributor_registry.profile_sections()) == 1


class TestComposition:
    def test_composition_installs_everything_the_users_namespace_asks_for(self):
        module_registry.configure_user_contributors()

        assert users_contributor_registry.erasers() is not None
        assert users_contributor_registry.lifecycle_hooks() is not None
        assert users_contributor_registry.profile_readers() is not None
        keys = [section.key for section in users_contributor_registry.profile_sections()]
        assert keys
        assert len(keys) == len(set(keys))

    def test_composing_again_replaces_the_installation_without_a_duplicate_section(self):
        module_registry.configure_user_contributors()
        first = [section.key for section in users_contributor_registry.profile_sections()]

        module_registry.configure_user_contributors()

        assert [section.key for section in users_contributor_registry.profile_sections()] == first
