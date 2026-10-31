"""Tests for users.users_default_gear.integration_service module."""

from unittest.mock import MagicMock, patch

import modules.users.users_default_gear.integration_service as user_default_gear_integration
import modules.users.users_default_gear.models as user_default_gear_models


@patch("modules.users.users_default_gear.integration_service.users_default_gear_crud")
class TestGetDefaultGearForActivityType:
    def test_returns_the_gear_for_the_activity_type(self, mock_crud):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        row.run_gear_id = 5
        mock_crud.get_user_default_gear_by_user_id.return_value = row

        assert user_default_gear_integration.get_default_gear_for_activity_type(1, 1, MagicMock()) == 5

    def test_returns_none_when_the_user_has_no_settings(self, mock_crud):
        mock_crud.get_user_default_gear_by_user_id.return_value = None

        assert user_default_gear_integration.get_default_gear_for_activity_type(1, 1, MagicMock()) is None

    def test_returns_none_for_an_unknown_activity_type(self, mock_crud):
        mock_crud.get_user_default_gear_by_user_id.return_value = MagicMock(
            spec=user_default_gear_models.UsersDefaultGear
        )

        assert user_default_gear_integration.get_default_gear_for_activity_type(1, 999, MagicMock()) is None

    def test_returns_none_when_the_gear_is_unset(self, mock_crud):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        row.ride_gear_id = None
        mock_crud.get_user_default_gear_by_user_id.return_value = row

        assert user_default_gear_integration.get_default_gear_for_activity_type(1, 4, MagicMock()) is None
