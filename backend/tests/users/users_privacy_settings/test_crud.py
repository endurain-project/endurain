"""Privacy settings against the real database: the defaults a new account gets, edits, and discovery opt-outs."""

import uuid

import pytest
from sqlalchemy import delete

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.users.users.models as users_models
import modules.users.users_privacy_settings.crud as crud
import modules.users.users_privacy_settings.schema as schema
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


class TestDefaults:
    def test_a_new_account_is_private_discoverable_and_hides_nothing(self, db, user):
        settings = crud.get_user_privacy_settings_by_user_id(user.id, db)

        assert settings is not None
        assert settings.default_activity_visibility == activity_constants.ActivityVisibility.PRIVATE
        assert settings.discoverable is True
        assert settings.version == 1
        hidden = [name for name, value in settings.model_dump().items() if name.startswith("hide_") and value]
        assert hidden == []

    def test_a_user_without_settings_reads_none(self, db):
        assert crud.get_user_privacy_settings_by_user_id(uuid.uuid4(), db) is None

    def test_a_second_row_for_a_user_is_a_conflict(self, db, user):
        with pytest.raises(core_exceptions.ConflictError):
            crud.create_user_privacy_settings(user.id, db)

    def test_deleting_the_user_deletes_the_settings(self, db, user):
        db.execute(delete(users_models.Users).where(users_models.Users.id == user.id))

        assert crud.get_user_privacy_settings_by_user_id(user.id, db) is None


class TestEdit:
    def test_only_the_set_fields_change_and_the_version_moves(self, db, user):
        update = schema.UserPrivacySettingsUpdate(
            default_activity_visibility=activity_constants.ActivityVisibility.FOLLOWERS, hide_activity_map=True
        )

        updated = crud.edit_user_privacy_settings(user.id, update, db, if_match='"1"')

        assert updated.default_activity_visibility == activity_constants.ActivityVisibility.FOLLOWERS
        assert updated.hide_activity_map is True
        assert updated.hide_activity_hr is False
        assert updated.discoverable is True
        assert updated.version == 2
        assert crud.get_user_privacy_settings_by_user_id(user.id, db) == updated

    def test_missing_settings_are_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_user_privacy_settings(
                uuid.uuid4(), schema.UserPrivacySettingsUpdate(hide_activity_map=True), db, if_match="*"
            )

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_user_privacy_settings(
                user.id, schema.UserPrivacySettingsUpdate(hide_activity_map=True), db, if_match='"4"'
            )

        stored = crud.get_user_privacy_settings_by_user_id(user.id, db)
        assert stored is not None
        assert stored.hide_activity_map is False


class TestListUndiscoverableUserIds:
    def test_only_the_users_who_switched_discovery_off_are_listed(self, db):
        hidden, visible = make_user(db), make_user(db)
        crud.edit_user_privacy_settings(
            hidden.id, schema.UserPrivacySettingsUpdate(discoverable=False), db, if_match="*"
        )

        listed = crud.list_undiscoverable_user_ids(db)

        assert hidden.id in listed
        assert visible.id not in listed
