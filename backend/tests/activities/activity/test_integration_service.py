"""Tests for the activities integration service — the provider-facing interface.

These verify each thin interface function delegates to the correct underlying
CRUD function with the arguments unchanged, so a miswiring is caught even though
the provider modules that call this in production (Strava/Garmin) mock it out.
"""

from unittest.mock import MagicMock, patch


class TestIntegrationService:
    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_get_activity_by_strava_id_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_activity_by_strava_id_from_user_id.return_value = "activity"

        result = integration_service.get_activity_by_strava_id(111, 3, db)

        assert result == "activity"
        mock_crud.get_activity_by_strava_id_from_user_id.assert_called_once_with(111, 3, db)

    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_get_activity_by_garminconnect_id_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_activity_by_garminconnect_id_from_user_id.return_value = "activity"

        result = integration_service.get_activity_by_garminconnect_id(222, 3, db)

        assert result == "activity"
        mock_crud.get_activity_by_garminconnect_id_from_user_id.assert_called_once_with(222, 3, db)

    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_list_user_activities_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_user_activities.return_value = ["a"]

        result = integration_service.list_user_activities(3, db)

        assert result == ["a"]
        mock_crud.get_user_activities.assert_called_once_with(3, db)

    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_list_user_activities_with_garminconnect_gear_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_user_activities_by_user_id_and_garminconnect_gear_set.return_value = ["a"]

        result = integration_service.list_user_activities_with_garminconnect_gear(3, db)

        assert result == ["a"]
        mock_crud.get_user_activities_by_user_id_and_garminconnect_gear_set.assert_called_once_with(3, db)

    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_bulk_set_activities_gear_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        assignments = {1: 10, 2: None}
        mock_crud.bulk_set_activities_gear_id.return_value = 2

        result = integration_service.bulk_set_activities_gear(3, assignments, db)

        assert result == 2
        mock_crud.bulk_set_activities_gear_id.assert_called_once_with(3, assignments, db)

    @patch("modules.activities.activity.integration_service.activities_crud")
    def test_delete_all_strava_activities_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.delete_all_strava_activities_for_user.return_value = 5

        result = integration_service.delete_all_strava_activities(3, db)

        assert result == 5
        mock_crud.delete_all_strava_activities_for_user.assert_called_once_with(3, db)
