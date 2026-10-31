"""Tests for users.users_default_gear.service module."""

from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_default_gear.service as user_default_gear_service


@patch("modules.users.users_default_gear.service.users_default_gear_crud")
@patch("modules.users.users_default_gear.service.gears_integration")
class TestEditDefaultGear:
    def test_checks_ownership_stages_and_commits(self, mock_gears, mock_crud, mock_db):
        update = user_default_gear_schema.UsersDefaultGearUpdate(run_gear_id=10)

        result = user_default_gear_service.edit_default_gear(update, 1, mock_db, if_match="*")

        assert result == mock_crud.edit_user_default_gear.return_value
        assert list(mock_gears.require_owned_gears.call_args.args[1]) == [10]
        mock_db.commit.assert_called_once()

    def test_refuses_a_gear_the_user_does_not_own(self, mock_gears, mock_crud, mock_db):
        update = user_default_gear_schema.UsersDefaultGearUpdate(run_gear_id=10)
        mock_gears.require_owned_gears.side_effect = core_exceptions.NotFoundError("Gear not found")

        with pytest.raises(core_exceptions.NotFoundError):
            user_default_gear_service.edit_default_gear(update, 1, mock_db, if_match="*")

        mock_crud.edit_user_default_gear.assert_not_called()
        mock_db.commit.assert_not_called()
