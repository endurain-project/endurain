"""Tests for the activity_ingestion enrichment seam (privacy / gear / Garmin resolution)."""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import modules.activities.activity_ingestion.enrichment as enrichment


def _privacy_settings() -> SimpleNamespace:
    """Privacy-settings DTO with one hidden field (hide_location) to prove mapping."""
    return SimpleNamespace(
        default_activity_visibility="public",
        hide_activity_start_time=False,
        hide_activity_location=True,
        hide_activity_map=False,
        hide_activity_hr=False,
        hide_activity_power=False,
        hide_activity_cadence=False,
        hide_activity_elevation=False,
        hide_activity_speed=False,
        hide_activity_pace=False,
        hide_activity_laps=False,
        hide_activity_workout_sets_steps=False,
        hide_activity_gear=False,
    )


class TestBuildActivityPrivacyKwargs:
    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_maps_privacy_fields(self, mock_users):
        mock_users.default_visibility_to_int.return_value = 0

        kwargs = enrichment.build_activity_privacy_kwargs(_privacy_settings())

        assert kwargs["visibility"] == 0
        assert kwargs["hide_location"] is True
        assert kwargs["hide_start_time"] is False
        # visibility + 12 hide_* flags.
        assert len(kwargs) == 13


class TestResolveGearId:
    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_default_gear_when_the_source_resolved_none(self, mock_users):
        mock_users.get_default_gear_for_activity_type.return_value = 42

        assert enrichment.resolve_gear_id(1, user_id=7, db=MagicMock()) == 42
        mock_users.get_default_gear_for_activity_type.assert_called_once_with(7, 1, ANY)

    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_none_activity_type_skips_default_gear(self, mock_users):
        assert enrichment.resolve_gear_id(None, user_id=7, db=MagicMock()) is None
        mock_users.get_default_gear_for_activity_type.assert_not_called()

    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_the_sources_gear_wins(self, mock_users):
        # The provider resolved its own synced gear; ingestion does not re-derive
        # it, which is what keeps this seam free of any provider import.
        assert enrichment.resolve_gear_id(1, user_id=7, db=MagicMock(), provider_gear_id=99) == 99
        mock_users.get_default_gear_for_activity_type.assert_not_called()

    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_falls_back_to_default_when_the_source_resolved_nothing(self, mock_users):
        mock_users.get_default_gear_for_activity_type.return_value = 5

        assert enrichment.resolve_gear_id(1, user_id=7, db=MagicMock(), provider_gear_id=None) == 5


class TestEnrichParsedActivity:
    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_sets_privacy_and_gear_non_garmin(self, mock_users):
        mock_users.default_visibility_to_int.return_value = 1
        mock_users.get_default_gear_for_activity_type.return_value = 12
        activity = SimpleNamespace(activity_type=4)

        enrichment.enrich_parsed_activity(
            activity, user_id=7, user_privacy_settings=_privacy_settings(), db=MagicMock()
        )

        assert activity.visibility == 1
        assert activity.hide_location is True
        assert activity.gear_id == 12
        # Non-Garmin import leaves the provider ids untouched.
        assert not hasattr(activity, "garminconnect_activity_id")

    @patch("modules.activities.activity_ingestion.enrichment.users_integration_service")
    def test_sets_garmin_ids_when_from_garmin(self, mock_users):
        mock_users.default_visibility_to_int.return_value = 0
        mock_users.get_default_gear_for_activity_type.return_value = None
        activity = SimpleNamespace(activity_type=1)

        enrichment.enrich_parsed_activity(
            activity,
            user_id=7,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
            from_garmin=True,
            garminconnect_gear_id="xyz",
            garmin_connect_activity_id=555,
        )

        assert activity.garminconnect_activity_id == 555
        assert activity.garminconnect_gear_id == "xyz"
