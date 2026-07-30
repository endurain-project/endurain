"""Tests for the activity exercise titles service layer."""

from unittest.mock import MagicMock, patch


class TestListActivityExerciseTitles:
    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    def test_delegates_to_crud(self, mock_crud):
        from modules.activities.activity_exercise_titles import service

        db = MagicMock()
        mock_crud.get_activity_exercise_titles.return_value = ["title"]

        assert service.list_activity_exercise_titles(db) == ["title"]
        mock_crud.get_activity_exercise_titles.assert_called_once_with(db)


class TestListPublicActivityExerciseTitles:
    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    @patch("modules.activities.activity_exercise_titles.service.server_settings_utils")
    def test_returns_titles_when_public_links_are_enabled(self, mock_settings, mock_crud):
        from modules.activities.activity_exercise_titles import service

        mock_settings.get_server_settings_or_404.return_value = MagicMock(public_shareable_links=True)
        mock_crud.get_activity_exercise_titles.return_value = ["title"]

        assert service.list_public_activity_exercise_titles(MagicMock()) == ["title"]

    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    @patch("modules.activities.activity_exercise_titles.service.server_settings_utils")
    def test_disabled_public_links_never_touch_persistence(self, mock_settings, mock_crud):
        from modules.activities.activity_exercise_titles import service

        mock_settings.get_server_settings_or_404.return_value = MagicMock(public_shareable_links=False)

        assert service.list_public_activity_exercise_titles(MagicMock()) == []
        mock_crud.get_activity_exercise_titles.assert_not_called()
