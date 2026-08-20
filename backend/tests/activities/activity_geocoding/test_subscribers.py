"""Tests for the geocoding subscribers (activity.created)."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from infra.events import new_event

_SUB = "modules.activities.activity_geocoding.subscribers"


def _event(payload):
    return new_event("activity.created", payload, source="test")


class TestOnActivityCreatedGeocode:
    """The bus wrapper: reverse-geocodes, swallowing any error."""

    @patch(f"{_SUB}.activity_geocoding_service")
    def test_noop_for_non_int_ids(self, mock_service):
        from modules.activities.activity_geocoding.subscribers import on_activity_created_geocode

        on_activity_created_geocode(_event({"activity_id": "x", "user_id": 2}))

        mock_service.geocode_and_store_activity_location.assert_not_called()

    @patch(f"{_SUB}.core_database")
    @patch(f"{_SUB}.activity_geocoding_service")
    def test_geocodes_for_activity(self, mock_service, _mock_db):
        from modules.activities.activity_geocoding.subscribers import on_activity_created_geocode

        on_activity_created_geocode(_event({"activity_id": 1, "user_id": 2}))

        assert mock_service.geocode_and_store_activity_location.call_args.args[0] == 1

    @patch("infra.subscribers.logger")
    @patch(f"{_SUB}.core_database")
    @patch(f"{_SUB}.activity_geocoding_service")
    def test_swallows_errors(self, mock_service, _mock_db, mock_logger):
        from modules.activities.activity_geocoding.subscribers import on_activity_created_geocode

        mock_service.geocode_and_store_activity_location.side_effect = RuntimeError("boom")

        # Must not raise — a geocoding failure never breaks activity import.
        on_activity_created_geocode(_event({"activity_id": 1, "user_id": 2}))

        mock_logger.error.assert_called()

    def test_subscribes_to_created(self):
        from modules.activities.activity_geocoding.subscribers import (
            on_activity_created_geocode,
            register_geocoding_subscribers,
        )

        events = MagicMock()
        register_geocoding_subscribers(events)

        events.subscribe.assert_called_once_with("activity.created", on_activity_created_geocode)


class TestGeocodeActivityForEvent:
    """The durable core: propagates errors so the job runner can retry."""

    @patch(f"{_SUB}.activity_geocoding_service")
    def test_raises_on_missing_ids(self, mock_service):
        from modules.activities.activity_geocoding.subscribers import geocode_activity_for_event

        with pytest.raises(ValidationError):
            geocode_activity_for_event(_event({"activity_id": 1}))

        mock_service.geocode_and_store_activity_location.assert_not_called()

    @patch(f"{_SUB}.core_database")
    @patch(f"{_SUB}.activity_geocoding_service")
    def test_raises_on_error(self, mock_service, _mock_db):
        from modules.activities.activity_geocoding.subscribers import geocode_activity_for_event

        mock_service.geocode_and_store_activity_location.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            geocode_activity_for_event(_event({"activity_id": 1, "user_id": 2}))

    def test_register_durable_handlers(self):
        from modules.activities.activity_geocoding.subscribers import (
            GEOCODING_SUBSCRIBER_ID,
            geocode_activity_for_event,
            register_geocoding_durable_handlers,
        )

        registry = MagicMock()
        register_geocoding_durable_handlers(registry)

        registry.register.assert_called_once_with(
            "activity.created",
            GEOCODING_SUBSCRIBER_ID,
            geocode_activity_for_event,
        )


class TestRunMissingLocationBackfill:
    """The scheduled reconciliation net: lock + batched backfill."""

    @patch(f"{_SUB}.logger")
    @patch(f"{_SUB}.platform_runtime")
    def test_skips_when_lock_not_acquired(self, mock_runtime, mock_logger):
        from modules.activities.activity_geocoding.subscribers import run_missing_location_backfill

        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = False
        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value = lock_cm

        run_missing_location_backfill()

        mock_logger.debug.assert_any_call(
            "Geocoding scheduler: another replica holds the backfill lock; skipping",
        )

    @patch(f"{_SUB}.core_database")
    @patch(f"{_SUB}.activity_geocoding_service")
    @patch(f"{_SUB}.platform_runtime")
    def test_runs_backfill_when_acquired(self, mock_runtime, mock_service, _mock_db):
        from modules.activities.activity_geocoding.subscribers import run_missing_location_backfill

        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = True
        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value = lock_cm
        mock_service.backfill_missing_activity_locations.return_value = 2

        run_missing_location_backfill()

        mock_service.backfill_missing_activity_locations.assert_called_once()
