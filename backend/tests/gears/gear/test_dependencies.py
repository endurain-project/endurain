"""Tests for gears.gear.dependencies.require_owned_gears."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.dependencies as gear_dependencies


@patch("modules.gears.gear.dependencies.gears_crud")
class TestRequireOwnedGears:
    """A client-supplied gear id is only accepted when it is the caller's."""

    def test_owned_gears_pass(self, mock_crud):
        mock_crud.get_gear_user_by_id.return_value = MagicMock()

        gear_dependencies.require_owned_gears(7, [1, 2], MagicMock())

        assert mock_crud.get_gear_user_by_id.call_count == 2

    def test_a_foreign_gear_is_not_found(self, mock_crud):
        mock_crud.get_gear_user_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            gear_dependencies.require_owned_gears(7, [1], MagicMock())

    def test_clearing_a_gear_needs_no_lookup(self, mock_crud):
        gear_dependencies.require_owned_gears(7, [None], MagicMock())

        mock_crud.get_gear_user_by_id.assert_not_called()

    def test_a_repeated_id_is_looked_up_once(self, mock_crud):
        mock_crud.get_gear_user_by_id.return_value = MagicMock()

        gear_dependencies.require_owned_gears(7, [3, 3, None], MagicMock())

        mock_crud.get_gear_user_by_id.assert_called_once()
