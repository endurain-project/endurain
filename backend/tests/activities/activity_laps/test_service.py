"""Tests for the activity laps service layer."""

from unittest.mock import MagicMock, patch


class TestListActivityLaps:
    @patch("modules.activities.activity_laps.service.activity_laps_crud")
    @patch("modules.activities.activity_laps.service.activity_child_access")
    def test_returns_laps_when_permitted(self, mock_gate, mock_crud):
        from modules.activities.activity_laps import service

        db = MagicMock()
        mock_gate.may_read_child.return_value = True
        mock_crud.get_activity_laps.return_value = ["lap"]

        assert service.list_activity_laps(5, 1, db) == ["lap"]
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_laps")

    @patch("modules.activities.activity_laps.service.activity_laps_crud")
    @patch("modules.activities.activity_laps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        """A refused read must not query, so it cannot leak timing or rows."""
        from modules.activities.activity_laps import service

        mock_gate.may_read_child.return_value = False

        assert service.list_activity_laps(5, 1, MagicMock()) == []
        mock_crud.get_activity_laps.assert_not_called()


class TestListPublicActivityLaps:
    @patch("modules.activities.activity_laps.service.activity_laps_crud")
    @patch("modules.activities.activity_laps.service.activity_child_access")
    def test_returns_laps_when_public(self, mock_gate, mock_crud):
        from modules.activities.activity_laps import service

        db = MagicMock()
        mock_gate.may_read_public_child.return_value = True
        mock_crud.get_activity_laps.return_value = ["lap"]

        assert service.list_public_activity_laps(5, db) == ["lap"]
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_laps")

    @patch("modules.activities.activity_laps.service.activity_laps_crud")
    @patch("modules.activities.activity_laps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_laps import service

        mock_gate.may_read_public_child.return_value = False

        assert service.list_public_activity_laps(5, MagicMock()) == []
        mock_crud.get_activity_laps.assert_not_called()
