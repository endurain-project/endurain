"""Tests for the activity exercise titles service layer."""

from unittest.mock import MagicMock, patch

import core.pagination as core_pagination


class TestListActivityExerciseTitles:
    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    def test_delegates_to_crud(self, mock_crud):
        from modules.activities.activity_exercise_titles import service

        db = MagicMock()
        mock_crud.get_activity_exercise_titles_page.return_value = []
        mock_crud.count_activity_exercise_titles.return_value = 450

        page = service.list_activity_exercise_titles(core_pagination.PageParams(2, 200), db)

        assert (page.total, page.page, page.next) == (450, 2, 3)
        mock_crud.get_activity_exercise_titles_page.assert_called_once_with(db, limit=200, offset=200)


class TestListPublicActivityExerciseTitles:
    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    @patch("modules.activities.activity_exercise_titles.service.server_settings_integration")
    def test_returns_titles_when_public_links_are_enabled(self, mock_settings, mock_crud):
        from modules.activities.activity_exercise_titles import service

        mock_settings.public_shareable_links_enabled.return_value = True
        mock_crud.get_activity_exercise_titles_page.return_value = []
        mock_crud.count_activity_exercise_titles.return_value = 3

        page = service.list_public_activity_exercise_titles(core_pagination.PageParams(1, 25), MagicMock())

        assert page.total == 3

    @patch("modules.activities.activity_exercise_titles.service.activity_exercise_titles_crud")
    @patch("modules.activities.activity_exercise_titles.service.server_settings_integration")
    def test_disabled_public_links_never_touch_persistence(self, mock_settings, mock_crud):
        from modules.activities.activity_exercise_titles import service

        mock_settings.public_shareable_links_enabled.return_value = False

        page = service.list_public_activity_exercise_titles(core_pagination.PageParams(1, 25), MagicMock())

        assert (page.items, page.total) == ([], 0)
        mock_crud.get_activity_exercise_titles_page.assert_not_called()
