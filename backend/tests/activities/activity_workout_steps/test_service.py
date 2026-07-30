"""Tests for the activity workout steps service layer."""

from unittest.mock import MagicMock, patch

from modules.activities.activity_workout_steps.schema import ActivityWorkoutSteps


def _item():
    """A minimal valid row; the page envelope validates its items."""
    return ActivityWorkoutSteps(message_index=1, duration_type="time")


class TestListActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_returns_a_page_when_permitted(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        db = MagicMock()
        mock_gate.may_read_child.return_value = True
        mock_crud.get_activity_workout_steps.return_value = [_item()]
        mock_crud.count_activity_workout_steps.return_value = 1

        page = service.list_activity_workout_steps(5, 1, db)

        assert len(page.items) == 1
        assert page.total == 1
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        """A refused read must not query, so it cannot leak timing or rows."""
        from modules.activities.activity_workout_steps import service

        mock_gate.may_read_child.return_value = False

        page = service.list_activity_workout_steps(5, 1, MagicMock())

        assert page.items == [] and page.total == 0
        mock_crud.get_activity_workout_steps.assert_not_called()
        mock_crud.count_activity_workout_steps.assert_not_called()

    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_paging_is_forwarded_and_the_total_spans_every_page(self, mock_gate, mock_crud):
        """``total`` must count all matching rows, not the slice returned."""
        from modules.activities.activity_workout_steps import service

        db = MagicMock()
        mock_gate.may_read_child.return_value = True
        mock_crud.get_activity_workout_steps.return_value = [_item()]
        mock_crud.count_activity_workout_steps.return_value = 250

        page = service.list_activity_workout_steps(5, 1, db, page_number=2, num_records=100)

        mock_crud.get_activity_workout_steps.assert_called_once_with(5, db, page_number=2, num_records=100)
        assert page.total == 250
        assert page.next == 3


class TestListPublicActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_returns_a_page_when_public(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        db = MagicMock()
        mock_gate.may_read_public_child.return_value = True
        mock_crud.get_activity_workout_steps.return_value = [_item()]
        mock_crud.count_activity_workout_steps.return_value = 1

        page = service.list_public_activity_workout_steps(5, db)

        assert len(page.items) == 1
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_workout_steps.service.activity_workout_steps_crud")
    @patch("modules.activities.activity_workout_steps.service.activity_child_access")
    def test_denied_never_touches_persistence(self, mock_gate, mock_crud):
        from modules.activities.activity_workout_steps import service

        mock_gate.may_read_public_child.return_value = False

        page = service.list_public_activity_workout_steps(5, MagicMock())

        assert page.items == [] and page.total == 0
        mock_crud.get_activity_workout_steps.assert_not_called()
