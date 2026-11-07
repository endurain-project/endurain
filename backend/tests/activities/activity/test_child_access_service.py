"""Tests for the shared child-resource authorization gate.

This is where the access rule for laps / sets / streams / workout steps now
lives; the four child CRUDs used to hold a copy each.
"""

from unittest.mock import MagicMock, patch


class TestIsHiddenFrom:
    """The hide rule, decided from an activity already in hand."""

    def test_the_owner_is_never_hidden_from(self):
        from types import SimpleNamespace

        from modules.activities.activity import child_access_service

        activity = SimpleNamespace(user_id=1, hide_laps=True)

        assert child_access_service.is_hidden_from(activity, 1, hide_attr="hide_laps") is False

    def test_a_non_owner_is_hidden_from_when_the_flag_is_set(self):
        from types import SimpleNamespace

        from modules.activities.activity import child_access_service

        activity = SimpleNamespace(user_id=1, hide_laps=True)

        assert child_access_service.is_hidden_from(activity, 2, hide_attr="hide_laps") is True

    def test_an_anonymous_viewer_is_hidden_from_when_the_flag_is_set(self):
        from types import SimpleNamespace

        from modules.activities.activity import child_access_service

        activity = SimpleNamespace(user_id=1, hide_laps=True)

        assert child_access_service.is_hidden_from(activity, None, hide_attr="hide_laps") is True

    def test_nobody_is_hidden_from_when_the_flag_is_unset(self):
        from types import SimpleNamespace

        from modules.activities.activity import child_access_service

        activity = SimpleNamespace(user_id=1, hide_laps=False)

        assert child_access_service.is_hidden_from(activity, 2, hide_attr="hide_laps") is False
        assert child_access_service.is_hidden_from(activity, None, hide_attr="hide_laps") is False


class TestResolveParents:
    @patch("modules.activities.activity.child_access_service.followers_integration")
    @patch("modules.activities.activity.child_access_service.server_settings_integration")
    @patch("modules.activities.activity.child_access_service.activity_crud")
    def test_readable_parent_is_unmasked(self, mock_crud, mock_settings, mock_followers):
        """Streams need the parent's hide_* flags to mask per stream type."""
        from modules.activities.activity import child_access_service

        db = MagicMock()
        activity = MagicMock()
        mock_crud.get_viewable_activity_by_id_for_user.return_value = activity

        assert child_access_service.resolve_readable_parent(5, 1, db) is activity

    @patch("modules.activities.activity.child_access_service.followers_integration")
    @patch("modules.activities.activity.child_access_service.server_settings_integration")
    @patch("modules.activities.activity.child_access_service.activity_crud")
    def test_public_parent_uses_the_public_read(self, mock_crud, mock_settings, mock_followers):
        from modules.activities.activity import child_access_service

        db = MagicMock()
        activity = MagicMock()
        mock_crud.get_activity_by_id_if_is_public.return_value = activity

        assert child_access_service.resolve_public_parent(5, db) is activity
        mock_crud.get_activity_by_id_if_is_public.assert_called_once_with(5, db)
