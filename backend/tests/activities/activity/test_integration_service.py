"""Tests for the activities integration service — the provider-facing interface.

These verify each thin interface function delegates to the correct underlying
CRUD function with the arguments unchanged, so a miswiring is caught even though
the provider modules that call this in production (Strava/Garmin) mock it out.
"""

from unittest.mock import MagicMock, patch


class TestIntegrationService:
    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_get_activity_by_strava_id_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_activity_by_strava_id_from_user_id.return_value = "activity"

        result = integration_service.get_activity_by_strava_id(111, 3, db)

        assert result == "activity"
        mock_crud.get_activity_by_strava_id_from_user_id.assert_called_once_with(111, 3, db)

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_get_activity_by_garminconnect_id_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_activity_by_garminconnect_id_from_user_id.return_value = "activity"

        result = integration_service.get_activity_by_garminconnect_id(222, 3, db)

        assert result == "activity"
        mock_crud.get_activity_by_garminconnect_id_from_user_id.assert_called_once_with(222, 3, db)

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_list_user_activities_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_user_activities.return_value = ["a"]

        result = integration_service.list_user_activities(3, db)

        assert result == ["a"]
        mock_crud.get_user_activities.assert_called_once_with(3, db, user_is_owner=True)

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_list_user_activities_with_garminconnect_gear_delegates(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.get_user_activities_by_user_id_and_garminconnect_gear_set.return_value = ["a"]

        result = integration_service.list_user_activities_with_garminconnect_gear(3, db)

        assert result == ["a"]
        mock_crud.get_user_activities_by_user_id_and_garminconnect_gear_set.assert_called_once_with(3, db)

    @patch("modules.activities.activity.integration_service.activity_service")
    def test_bulk_set_activities_gear_delegates(self, mock_service):
        """The surface names the caller; the service arranges the write."""
        from modules.activities.activity import integration_service

        db = MagicMock()
        assignments = {1: 10, 2: None}
        mock_service.bulk_set_activities_gear.return_value = 2

        result = integration_service.bulk_set_activities_gear(3, assignments, db)

        assert result == 2
        mock_service.bulk_set_activities_gear.assert_called_once_with(
            3, assignments, db, source="api:bulk_set_activities_gear"
        )

    @patch("modules.activities.activity.integration_service.activity_service")
    def test_delete_all_strava_activities_delegates(self, mock_service):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_service.delete_all_strava_activities.return_value = 5

        result = integration_service.delete_all_strava_activities(3, db)

        assert result == 5
        mock_service.delete_all_strava_activities.assert_called_once_with(
            3, db, source="api:delete_all_strava_activities"
        )

    @patch("modules.activities.activity.integration_service.activity_service")
    def test_delete_all_activities_for_user_delegates(self, mock_service):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_service.delete_all_activities_for_user.return_value = 2

        result = integration_service.delete_all_activities_for_user(7, db)

        assert result == 2
        mock_service.delete_all_activities_for_user.assert_called_once_with(7, db, source="api:delete_user")


class TestDerivedArtifactWritesStageOnly:
    """The thumbnail and geocoding writes stage in CRUD; the caller commits.

    A cross-module call must not end the caller's transaction, so none of these
    commits or rolls back.
    """

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_set_thumbnail_key_stages_without_committing(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        integration_service.set_thumbnail_key(7, "7.png", db)

        mock_crud.set_activity_thumbnail_key.assert_called_once_with(7, "7.png", db, expected_key=None)
        db.commit.assert_not_called()
        db.rollback.assert_not_called()

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_clear_all_thumbnail_keys_stages_without_committing(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        integration_service.clear_all_thumbnail_keys(db)

        mock_crud.clear_all_activity_thumbnail_keys.assert_called_once_with(db)
        db.commit.assert_not_called()

    @patch("modules.activities.activity.integration_service.activity_crud")
    def test_set_activity_location_reports_whether_a_row_changed(self, mock_crud):
        from modules.activities.activity import integration_service

        db = MagicMock()
        mock_crud.update_activity_location.return_value = True
        assert integration_service.set_activity_location(7, "Lisbon", None, "Portugal", db) is True
        mock_crud.update_activity_location.return_value = False
        assert integration_service.set_activity_location(999, "Lisbon", None, "Portugal", db) is False

        mock_crud.update_activity_location.assert_called_with(999, "Lisbon", None, "Portugal", db)
        db.commit.assert_not_called()
