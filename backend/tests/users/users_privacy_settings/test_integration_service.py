"""Tests for the users_privacy_settings surface."""

import pytest

import modules.activities.activity.constants as activity_constants
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as schema
from tests._factories.users import make_user


class TestResolveVisibility:
    @pytest.mark.parametrize(
        ("visibility", "expected"),
        [
            ("public", activity_constants.ActivityVisibility.PUBLIC),
            ("followers", activity_constants.ActivityVisibility.FOLLOWERS),
            ("private", activity_constants.ActivityVisibility.PRIVATE),
            (activity_constants.ActivityVisibility.PUBLIC, activity_constants.ActivityVisibility.PUBLIC),
            (activity_constants.ActivityVisibility.FOLLOWERS, activity_constants.ActivityVisibility.FOLLOWERS),
            (activity_constants.ActivityVisibility.PRIVATE, activity_constants.ActivityVisibility.PRIVATE),
        ],
    )
    def test_known_levels(self, visibility, expected):
        assert privacy_integration.resolve_visibility(visibility) is expected

    @pytest.mark.parametrize("visibility", [None, "", "everyone", "PUBLIC"])
    def test_unset_or_unrecognized_fails_closed_to_private(self, visibility):
        assert privacy_integration.resolve_visibility(visibility) is activity_constants.ActivityVisibility.PRIVATE


class TestEditPrivacySettings:
    def test_the_settings_are_read_back_after_an_overwrite(self, db):
        user = make_user(db)

        edited = privacy_integration.edit_privacy_settings(
            user.id, schema.UserPrivacySettingsUpdate(hide_activity_gear=True), db, if_match="*"
        )

        assert privacy_integration.get_privacy_settings(user.id, db) == edited
        assert edited.hide_activity_gear is True
        assert user.id not in privacy_integration.list_undiscoverable_user_ids(db)
