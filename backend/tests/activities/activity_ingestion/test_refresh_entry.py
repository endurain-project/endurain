"""Tests for the provider-refresh entry point."""

from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_ingestion.refresh_entry as refresh_entry


class TestSyncLinkedProviders:
    @pytest.mark.asyncio
    async def test_combines_both_providers(self):
        db = MagicMock()
        with (
            patch.object(refresh_entry.strava_activity_utils, "get_user_strava_activities_by_dates") as strava,
            patch.object(refresh_entry.garmin_activity_utils, "get_user_garminconnect_activities_by_dates") as garmin,
            patch.object(refresh_entry.websocket_manager, "get_websocket_manager", return_value="ws"),
        ):

            async def _strava(**_kwargs):
                return ["s1"]

            async def _garmin(**_kwargs):
                return ["g1"]

            strava.side_effect = _strava
            garmin.side_effect = _garmin
            result = await refresh_entry.sync_linked_providers(7, db)

        assert result == ["s1", "g1"]

    @pytest.mark.asyncio
    async def test_an_unlinked_provider_returns_nothing_rather_than_failing(self):
        """One unlinked integration must not fail the whole refresh."""
        db = MagicMock()
        with (
            patch.object(refresh_entry.strava_activity_utils, "get_user_strava_activities_by_dates") as strava,
            patch.object(refresh_entry.garmin_activity_utils, "get_user_garminconnect_activities_by_dates") as garmin,
            patch.object(refresh_entry.websocket_manager, "get_websocket_manager", return_value="ws"),
        ):

            async def _strava(**_kwargs):
                return None

            async def _garmin(**_kwargs):
                return ["g1"]

            strava.side_effect = _strava
            garmin.side_effect = _garmin
            result = await refresh_entry.sync_linked_providers(7, db)

        assert result == ["g1"]

    @pytest.mark.asyncio
    async def test_uses_the_process_local_websocket_manager(self):
        """There is no request here, so the manager cannot come from a dependency."""
        db = MagicMock()
        with (
            patch.object(refresh_entry.strava_activity_utils, "get_user_strava_activities_by_dates") as strava,
            patch.object(refresh_entry.garmin_activity_utils, "get_user_garminconnect_activities_by_dates") as garmin,
            patch.object(refresh_entry.websocket_manager, "get_websocket_manager", return_value="ws") as get_ws,
        ):

            async def _none(**_kwargs):
                return None

            strava.side_effect = _none
            garmin.side_effect = _none
            await refresh_entry.sync_linked_providers(7, db)

        get_ws.assert_called_once()
        assert garmin.call_args.kwargs["ws_manager"] == "ws"

    @pytest.mark.asyncio
    async def test_asks_both_providers_for_the_same_window(self):
        db = MagicMock()
        with (
            patch.object(refresh_entry.strava_activity_utils, "get_user_strava_activities_by_dates") as strava,
            patch.object(refresh_entry.garmin_activity_utils, "get_user_garminconnect_activities_by_dates") as garmin,
            patch.object(refresh_entry.websocket_manager, "get_websocket_manager", return_value="ws"),
        ):

            async def _none(**_kwargs):
                return None

            strava.side_effect = _none
            garmin.side_effect = _none
            await refresh_entry.sync_linked_providers(7, db)

        assert strava.call_args.kwargs["start_date"] == garmin.call_args.kwargs["start_date"]
        assert strava.call_args.kwargs["end_date"] == garmin.call_args.kwargs["end_date"]
        window = strava.call_args.kwargs["end_date"] - strava.call_args.kwargs["start_date"]
        assert window == refresh_entry._REFRESH_WINDOW
