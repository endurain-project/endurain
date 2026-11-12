"""Tests for users.users_default_gear.integration_service module."""

import uuid
from unittest.mock import MagicMock, patch

import modules.users.users_default_gear.integration_service as user_default_gear_integration
import modules.users.users_default_gear.models as user_default_gear_models

_GEAR_A = uuid.uuid4()
_GEAR_B = uuid.uuid4()


@patch("modules.users.users_default_gear.integration_service.users_default_gear_crud")
class TestGetDefaultGearForActivityType:
    def test_returns_the_gear_for_the_activity_type(self, mock_crud):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        row.run_gear_id = _GEAR_A
        mock_crud.get_user_default_gear_by_user_id.return_value = row

        assert user_default_gear_integration.get_default_gear_for_activity_type(1, 1, MagicMock()) == _GEAR_A

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


@patch("modules.users.users_default_gear.integration_service.users_default_gear_crud")
def test_clear_default_gears_stages_through_the_crud(mock_crud):
    db = MagicMock()

    user_default_gear_integration.clear_default_gears([_GEAR_A, _GEAR_B], 1, db)

    mock_crud.clear_gears.assert_called_once_with([_GEAR_A, _GEAR_B], 1, db)
