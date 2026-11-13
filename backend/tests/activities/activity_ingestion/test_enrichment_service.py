"""Tests for the activity_ingestion enrichment seam (privacy / gear / Garmin resolution)."""

import uuid
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from tests._helpers.auth import MOCK_USER_ID

import modules.activities.activity_ingestion.enrichment_service as enrichment
from modules.activities.activity.constants import ActivityType, ActivityVisibility


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
    @patch("modules.activities.activity_ingestion.enrichment_service.users_privacy_settings_integration")
    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_maps_privacy_fields(self, mock_users, mock_privacy):
        mock_privacy.resolve_visibility.return_value = ActivityVisibility.PUBLIC

        kwargs = enrichment.build_activity_privacy_kwargs(_privacy_settings())

        assert kwargs["visibility"] is ActivityVisibility.PUBLIC
        assert kwargs["hide_location"] is True
        assert kwargs["hide_start_time"] is False
        # visibility + 12 hide_* flags.
        assert len(kwargs) == 13


_DEFAULT_GEAR = uuid.uuid4()
_SOURCE_GEAR = uuid.uuid4()


class TestResolveGearId:
    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_default_gear_when_the_source_resolved_none(self, mock_users):
        mock_users.get_default_gear_for_activity_type.return_value = _DEFAULT_GEAR

        assert enrichment.resolve_gear_id(1, user_id=MOCK_USER_ID, db=MagicMock()) == _DEFAULT_GEAR
        mock_users.get_default_gear_for_activity_type.assert_called_once_with(MOCK_USER_ID, 1, ANY)

    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_none_activity_type_skips_default_gear(self, mock_users):
        assert enrichment.resolve_gear_id(None, user_id=MOCK_USER_ID, db=MagicMock()) is None
        mock_users.get_default_gear_for_activity_type.assert_not_called()

    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_the_sources_gear_wins(self, mock_users):
        # The provider resolved its own synced gear; ingestion does not re-derive
        # it, which is what keeps this seam free of any provider import.
        assert (
            enrichment.resolve_gear_id(1, user_id=MOCK_USER_ID, db=MagicMock(), provider_gear_id=_SOURCE_GEAR)
            == _SOURCE_GEAR
        )
        mock_users.get_default_gear_for_activity_type.assert_not_called()

    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_falls_back_to_default_when_the_source_resolved_nothing(self, mock_users):
        mock_users.get_default_gear_for_activity_type.return_value = _DEFAULT_GEAR

        assert (
            enrichment.resolve_gear_id(1, user_id=MOCK_USER_ID, db=MagicMock(), provider_gear_id=None) == _DEFAULT_GEAR
        )


class TestEnrichParsedActivity:
    @patch("modules.activities.activity_ingestion.enrichment_service.users_privacy_settings_integration")
    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_sets_privacy_and_gear_non_garmin(self, mock_users, mock_privacy):
        mock_privacy.resolve_visibility.return_value = ActivityVisibility.FOLLOWERS
        mock_users.get_default_gear_for_activity_type.return_value = _DEFAULT_GEAR
        activity = SimpleNamespace(activity_type=ActivityType.RIDE)

        enrichment.enrich_parsed_activity(
            activity, user_id=MOCK_USER_ID, user_privacy_settings=_privacy_settings(), db=MagicMock()
        )

        assert activity.visibility is ActivityVisibility.FOLLOWERS
        assert activity.hide_location is True
        assert activity.gear_id == _DEFAULT_GEAR
        # Non-Garmin import leaves the provider ids untouched.
        assert not hasattr(activity, "garminconnect_activity_id")

    @patch("modules.activities.activity_ingestion.enrichment_service.users_privacy_settings_integration")
    @patch("modules.activities.activity_ingestion.enrichment_service.users_default_gear_integration")
    def test_sets_garmin_ids_when_from_garmin(self, mock_users, mock_privacy):
        mock_privacy.resolve_visibility.return_value = ActivityVisibility.PUBLIC
        mock_users.get_default_gear_for_activity_type.return_value = None
        activity = SimpleNamespace(activity_type=ActivityType.RUN)

        enrichment.enrich_parsed_activity(
            activity,
            user_id=MOCK_USER_ID,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
            from_garmin=True,
            garminconnect_gear_id="xyz",
            garmin_connect_activity_id=555,
        )

        assert activity.garminconnect_activity_id == 555
        assert activity.garminconnect_gear_id == "xyz"
