"""Tests for users.users_default_gear.service module."""

import uuid
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_default_gear.service as user_default_gear_service

_GEAR_A = uuid.uuid4()
_GEAR_B = uuid.uuid4()
_NEW_A = uuid.uuid4()
_NEW_B = uuid.uuid4()


@patch("modules.users.users_default_gear.service.users_default_gear_crud")
@patch("modules.users.users_default_gear.service.gears_integration")
class TestEditDefaultGear:
    def test_checks_ownership_stages_and_commits(self, mock_gears, mock_crud, mock_db):
        update = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=_GEAR_A)

        result = user_default_gear_service.edit_default_gear(update, 1, mock_db, if_match="*")

        assert result == mock_crud.edit_user_default_gear.return_value
        assert list(mock_gears.require_owned_gears.call_args.args[1]) == [_GEAR_A]
        mock_db.commit.assert_called_once()

    def test_refuses_a_gear_the_user_does_not_own(self, mock_gears, mock_crud, mock_db):
        update = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=_GEAR_A)
        mock_gears.require_owned_gears.side_effect = core_exceptions.NotFoundError("Gear not found")

        with pytest.raises(core_exceptions.NotFoundError):
            user_default_gear_service.edit_default_gear(update, 1, mock_db, if_match="*")

        mock_crud.edit_user_default_gear.assert_not_called()
        mock_db.commit.assert_not_called()


@patch("modules.users.users_default_gear.service.stage_default_gear_edit")
@patch("modules.users.users_default_gear.service.users_default_gear_crud")
class TestRestoreProfileDefaultGear:
    def test_creates_the_settings_when_missing_and_remaps_the_gears(self, mock_crud, mock_edit, mock_db):
        mock_crud.get_user_default_gear_by_user_id.return_value = None

        restored = user_default_gear_service.restore_profile_default_gear(
            {"id": 3, "user_id": 9, "version": 2, "run_gear_id": str(_GEAR_A), "ride_gear_id": str(_GEAR_B)},
            {"gears": {str(_GEAR_A): _NEW_A, str(_GEAR_B): _NEW_B}},
            1,
            mock_db,
        )

        assert restored is True
        mock_crud.create_user_default_gear.assert_called_once_with(1, mock_db)
        update = mock_edit.call_args.args[0]
        assert (update.run_gear_id, update.ride_gear_id, update.walk_gear_id) == (_NEW_A, _NEW_B, None)
        assert mock_edit.call_args.kwargs == {"if_match": "*"}

    def test_keeps_existing_settings_and_drops_an_unmapped_gear(self, mock_crud, mock_edit, mock_db):
        restored = user_default_gear_service.restore_profile_default_gear(
            {"run_gear_id": str(_GEAR_A)}, {"gears": {}}, 1, mock_db
        )

        assert restored is True
        mock_crud.create_user_default_gear.assert_not_called()
        assert mock_edit.call_args.args[0].run_gear_id is None

    def test_skips_invalid_settings(self, mock_crud, mock_edit, mock_db):
        restored = user_default_gear_service.restore_profile_default_gear({"unknown_field": 1}, {}, 1, mock_db)

        assert restored is False
        mock_edit.assert_not_called()
