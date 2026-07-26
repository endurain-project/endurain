"""The athlete's own timezone drives every "which day is it?" question."""

from datetime import date
from unittest.mock import MagicMock, patch

import modules.users.users.utils as users_utils


class TestResolveUserTimezone:
    @patch("modules.users.users.utils.users_crud.get_user_by_id")
    def test_prefers_the_users_own_zone(self, mock_get_user):
        mock_get_user.return_value = MagicMock(timezone="America/Los_Angeles")
        assert users_utils.resolve_user_timezone(1, MagicMock()) == "America/Los_Angeles"

    @patch("modules.users.users.utils.core_config")
    @patch("modules.users.users.utils.users_crud.get_user_by_id")
    def test_falls_back_to_the_server_zone_when_unset(self, mock_get_user, mock_config):
        """Accounts predating the setting have none; the server default is all we have."""
        mock_get_user.return_value = MagicMock(timezone=None)
        mock_config.settings.TZ = "Europe/Lisbon"
        assert users_utils.resolve_user_timezone(1, MagicMock()) == "Europe/Lisbon"

    @patch("modules.users.users.utils.core_config")
    @patch("modules.users.users.utils.users_crud.get_user_by_id")
    def test_falls_back_when_the_user_is_missing(self, mock_get_user, mock_config):
        mock_get_user.return_value = None
        mock_config.settings.TZ = "Europe/Lisbon"
        assert users_utils.resolve_user_timezone(1, MagicMock()) == "Europe/Lisbon"


class TestUserLocalToday:
    @patch("modules.users.users.utils.resolve_user_timezone", return_value="Asia/Tokyo")
    def test_resolves_today_in_the_users_zone(self, _mock_tz):
        result = users_utils.user_local_today(1, MagicMock())
        assert isinstance(result, date)

    @patch("modules.users.users.utils.core_timezone.today_in")
    @patch("modules.users.users.utils.resolve_user_timezone", return_value="Asia/Tokyo")
    def test_uses_the_resolved_zone_not_the_server_clock(self, _mock_tz, mock_today):
        mock_today.return_value = date(2024, 1, 15)
        assert users_utils.user_local_today(1, MagicMock()) == date(2024, 1, 15)
        mock_today.assert_called_once_with("Asia/Tokyo")
