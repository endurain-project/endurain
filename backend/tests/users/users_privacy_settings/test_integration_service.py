"""Tests for the users_privacy_settings surface."""

import pytest

import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as privacy_schema


class TestVisibilityToInt:
    @pytest.mark.parametrize(
        ("visibility", "expected"),
        [
            ("public", 0),
            ("followers", 1),
            ("private", 2),
            (privacy_schema.ActivityVisibility.PUBLIC, 0),
            (privacy_schema.ActivityVisibility.FOLLOWERS, 1),
            (privacy_schema.ActivityVisibility.PRIVATE, 2),
        ],
    )
    def test_known_levels(self, visibility, expected):
        assert privacy_integration.visibility_to_int(visibility) == expected

    @pytest.mark.parametrize("visibility", [None, "", "everyone", "PUBLIC"])
    def test_unset_or_unrecognized_fails_closed_to_private(self, visibility):
        assert privacy_integration.visibility_to_int(visibility) == 2
