"""Tests for the shared child-resource authorization gate.

This is where the access rule for laps / sets / streams / workout steps now
lives; the four child CRUDs used to hold a copy each.
"""

from unittest.mock import MagicMock, patch


class TestMayReadChild:
    @patch("modules.activities.activity.child_access.activities_crud")
    def test_owner_may_read_even_when_the_flag_is_set(self, mock_crud):
        from modules.activities.activity import child_access

        mock_crud.get_viewable_activity_by_id_for_user.return_value = MagicMock(user_id=1, hide_laps=True)

        assert child_access.may_read_child(5, 1, MagicMock(), hide_attr="hide_laps") is True

    @patch("modules.activities.activity.child_access.activities_crud")
    def test_non_owner_is_denied_when_the_flag_is_set(self, mock_crud):
        from modules.activities.activity import child_access

        mock_crud.get_viewable_activity_by_id_for_user.return_value = MagicMock(user_id=2, hide_laps=True)

        assert child_access.may_read_child(5, 1, MagicMock(), hide_attr="hide_laps") is False

    @patch("modules.activities.activity.child_access.activities_crud")
    def test_non_owner_may_read_when_the_flag_is_unset(self, mock_crud):
        from modules.activities.activity import child_access

        mock_crud.get_viewable_activity_by_id_for_user.return_value = MagicMock(user_id=2, hide_laps=False)

        assert child_access.may_read_child(5, 1, MagicMock(), hide_attr="hide_laps") is True

    @patch("modules.activities.activity.child_access.activities_crud")
    def test_an_invisible_activity_is_denied(self, mock_crud):
        """A private / non-followed activity must not leak its children (IDOR)."""
        from modules.activities.activity import child_access

        mock_crud.get_viewable_activity_by_id_for_user.return_value = None

        assert child_access.may_read_child(5, 1, MagicMock(), hide_attr="hide_laps") is False


class TestMayReadPublicChild:
    @patch("modules.activities.activity.child_access.activities_crud")
    def test_delegates_to_the_public_gate(self, mock_crud):
        from modules.activities.activity import child_access

        db = MagicMock()
        mock_crud.get_public_activity_for_child_read.return_value = MagicMock()

        assert child_access.may_read_public_child(5, db, hide_attr="hide_laps") is True
        mock_crud.get_public_activity_for_child_read.assert_called_once_with(5, db, hide_attr="hide_laps")

    @patch("modules.activities.activity.child_access.activities_crud")
    def test_gate_refusal_is_a_refusal(self, mock_crud):
        from modules.activities.activity import child_access

        mock_crud.get_public_activity_for_child_read.return_value = None

        assert child_access.may_read_public_child(5, MagicMock(), hide_attr="hide_laps") is False


class TestResolveParents:
    @patch("modules.activities.activity.child_access.activities_crud")
    def test_readable_parent_is_unmasked(self, mock_crud):
        """Streams need the parent's hide_* flags to mask per stream type."""
        from modules.activities.activity import child_access

        db = MagicMock()
        activity = MagicMock()
        mock_crud.get_viewable_activity_by_id_for_user.return_value = activity

        assert child_access.resolve_readable_parent(5, 1, db) is activity

    @patch("modules.activities.activity.child_access.activities_crud")
    def test_public_parent_uses_the_public_read(self, mock_crud):
        from modules.activities.activity import child_access

        db = MagicMock()
        activity = MagicMock()
        mock_crud.get_activity_by_id_if_is_public.return_value = activity

        assert child_access.resolve_public_parent(5, db) is activity
        mock_crud.get_activity_by_id_if_is_public.assert_called_once_with(5, db)
