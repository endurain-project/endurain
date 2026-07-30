"""Tests for the activity workout steps service layer."""

from unittest.mock import MagicMock, patch


class TestListActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_returns_steps_when_permitted(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        db = MagicMock()
        mock_gate.may_read_child.return_value = True
        mock_crud.get_activity_workout_steps.return_value = ["step"]

        assert service.list_activity_workout_steps(5, 1, db) == ["step"]
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        mock_gate.may_read_child.return_value = False

        assert service.list_activity_workout_steps(5, 1, MagicMock()) == []
        mock_crud.get_activity_workout_steps.assert_not_called()


class TestListPublicActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_returns_steps_when_public(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        db = MagicMock()
        mock_gate.may_read_public_child.return_value = True
        mock_crud.get_activity_workout_steps.return_value = ["step"]

        assert service.list_public_activity_workout_steps(5, db) == ["step"]
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        mock_gate.may_read_public_child.return_value = False

        assert service.list_public_activity_workout_steps(5, MagicMock()) == []
        mock_crud.get_activity_workout_steps.assert_not_called()
