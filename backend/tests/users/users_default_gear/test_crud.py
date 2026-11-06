"""Tests for users.users_default_gear.crud module."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.users.users_default_gear.crud as user_default_gear_crud
import modules.users.users_default_gear.models as user_default_gear_models
import modules.users.users_default_gear.schema as user_default_gear_schema


@pytest.fixture(autouse=True)
def _patch_serializer():
    """Patch the serializer to a passthrough for MagicMock compatibility."""
    with patch(
        "modules.users.users_default_gear.crud.users_default_gear_serializers.to_read_schema",
        side_effect=lambda x: x,
    ):
        yield


def _found(mock_db, row):
    """Make the session's SELECT return ``row`` (or None)."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = mock_result


class TestGetUserDefaultGearByUserId:
    def test_returns_the_settings(self, mock_db):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        _found(mock_db, row)

        assert user_default_gear_crud.get_user_default_gear_by_user_id(1, mock_db) == row

    def test_returns_none_when_missing(self, mock_db):
        _found(mock_db, None)

        assert user_default_gear_crud.get_user_default_gear_by_user_id(1, mock_db) is None


class TestCreateUserDefaultGear:
    def test_stages_without_committing(self, mock_db):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)

        with patch.object(user_default_gear_models, "UsersDefaultGear", return_value=row):
            result = user_default_gear_crud.create_user_default_gear(1, mock_db)

        assert result == row
        mock_db.add.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_is_a_conflict(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("Duplicate entry", None, None)

        with pytest.raises(core_exceptions.ConflictError):
            user_default_gear_crud.create_user_default_gear(1, mock_db)


class TestEditUserDefaultGear:
    def test_applies_the_set_fields_and_stages(self, mock_db):
        row = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        _found(mock_db, row)
        update = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=10)

        result = user_default_gear_crud.edit_user_default_gear(update, 1, mock_db, if_match="*")

        assert result == row
        assert row.run_gear_id == 10
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_settings_are_not_found(self, mock_db):
        _found(mock_db, None)
        update = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=10)

        with pytest.raises(core_exceptions.NotFoundError):
            user_default_gear_crud.edit_user_default_gear(update, 1, mock_db, if_match="*")


class TestClearGears:
    def test_stages_one_update_that_bumps_the_version(self, mock_db):
        user_default_gear_crud.clear_gears([3], 1, mock_db)

        stmt = mock_db.execute.call_args.args[0]
        compiled = str(stmt.compile())
        assert "version=" in compiled.replace(" ", "") or "version = " in compiled
        assert "run_gear_id" in compiled and "windsurf_gear_id" in compiled
        mock_db.flush.assert_called_once()

    def test_does_nothing_without_gears(self, mock_db):
        user_default_gear_crud.clear_gears([], 1, mock_db)

        mock_db.execute.assert_not_called()
