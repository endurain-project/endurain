"""Tests for the activity sets service layer."""

from unittest.mock import MagicMock, patch


class TestListActivitySets:
    @patch("modules.activities.activity_sets.service.activity_sets_crud")
    @patch("modules.activities.activity_sets.service.activity_child_access")
    def test_returns_sets_when_permitted(self, mock_gate, mock_crud):
        from modules.activities.activity_sets import service

        db = MagicMock()
        mock_gate.may_read_child.return_value = True
        mock_crud.get_activity_sets.return_value = ["set"]

        assert service.list_activity_sets(5, 1, db) == ["set"]
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_sets.service.activity_sets_crud")
    @patch("modules.activities.activity_sets.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_sets import service

        mock_gate.may_read_child.return_value = False

        assert service.list_activity_sets(5, 1, MagicMock()) == []
        mock_crud.get_activity_sets.assert_not_called()


class TestListPublicActivitySets:
    @patch("modules.activities.activity_sets.service.activity_sets_crud")
    @patch("modules.activities.activity_sets.service.activity_child_access")
    def test_returns_sets_when_public(self, mock_gate, mock_crud):
        from modules.activities.activity_sets import service

        db = MagicMock()
        mock_gate.may_read_public_child.return_value = True
        mock_crud.get_activity_sets.return_value = ["set"]

        assert service.list_public_activity_sets(5, db) == ["set"]
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_sets.service.activity_sets_crud")
    @patch("modules.activities.activity_sets.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_sets import service

        mock_gate.may_read_public_child.return_value = False

        assert service.list_public_activity_sets(5, MagicMock()) == []
        mock_crud.get_activity_sets.assert_not_called()
