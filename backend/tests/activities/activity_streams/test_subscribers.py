"""Tests for the HR-zone subscribers (activity.created)."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from infra.events import new_event


def _event(payload):
    return new_event("activity.created", payload, source="test")


class TestOnActivityCreatedComputeHrZones:
    """The bus wrapper: computes HR zones, swallowing any error."""

    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    def test_noop_for_non_int_ids(self, mock_service):
        from modules.activities.activity_streams.subscribers import on_activity_created_compute_hr_zones

        on_activity_created_compute_hr_zones(_event({"activity_id": "x", "user_id": 2}))

        mock_service.score_activity_hr_zones.assert_not_called()

    @patch("modules.activities.activity_streams.subscribers.core_database")
    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    def test_computes_for_activity(self, mock_service, mock_db):
        from modules.activities.activity_streams.subscribers import on_activity_created_compute_hr_zones

        on_activity_created_compute_hr_zones(_event({"activity_id": 1, "user_id": 2}))

        assert mock_service.score_activity_hr_zones.call_args.args[:2] == (1, 2)

    @patch("infra.subscribers.logger")
    @patch("modules.activities.activity_streams.subscribers.core_database")
    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    def test_swallows_errors(self, mock_service, mock_db, mock_logger):
        from modules.activities.activity_streams.subscribers import on_activity_created_compute_hr_zones

        mock_service.score_activity_hr_zones.side_effect = RuntimeError("boom")

        # Must not raise — an HR-zone failure never breaks activity import.
        on_activity_created_compute_hr_zones(_event({"activity_id": 1, "user_id": 2}))

        mock_logger.error.assert_called()

    def test_subscribes_to_created(self):
        from modules.activities.activity_streams.subscribers import (
            on_activity_created_compute_hr_zones,
            register_hr_zone_subscribers,
        )

        events = MagicMock()
        register_hr_zone_subscribers(events)

        events.subscribe.assert_called_once_with("activity.created", on_activity_created_compute_hr_zones)


class TestComputeHrZonesForEvent:
    """The durable core: propagates errors so the job runner can retry."""

    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    def test_raises_on_missing_ids(self, mock_service):
        from modules.activities.activity_streams.subscribers import compute_hr_zones_for_event

        with pytest.raises(ValidationError):
            compute_hr_zones_for_event(_event({"activity_id": 1}))

        mock_service.score_activity_hr_zones.assert_not_called()

    @patch("modules.activities.activity_streams.subscribers.core_database")
    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    def test_raises_on_error(self, mock_service, mock_db):
        from modules.activities.activity_streams.subscribers import compute_hr_zones_for_event

        mock_service.score_activity_hr_zones.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            compute_hr_zones_for_event(_event({"activity_id": 1, "user_id": 2}))

    def test_register_durable_handlers(self):
        from modules.activities.activity_streams.subscribers import (
            HR_ZONE_SUBSCRIBER_ID,
            compute_hr_zones_for_event,
            register_hr_zone_durable_handlers,
        )

        registry = MagicMock()
        register_hr_zone_durable_handlers(registry)

        registry.register.assert_called_once_with(
            "activity.created",
            HR_ZONE_SUBSCRIBER_ID,
            compute_hr_zones_for_event,
        )


class TestRunMissingHrZoneBackfill:
    """The scheduled reconciliation net: lock + batched backfill."""

    @patch("modules.activities.activity_streams.subscribers.logger")
    @patch("modules.activities.activity_streams.subscribers.platform_runtime")
    def test_skips_when_lock_not_acquired(self, mock_runtime, mock_logger):
        from modules.activities.activity_streams.subscribers import run_missing_hr_zone_backfill

        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = False
        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value = lock_cm

        run_missing_hr_zone_backfill()

        mock_logger.debug.assert_any_call(
            "HR-zone scheduler: another replica holds the backfill lock; skipping",
        )

    @patch("modules.activities.activity_streams.subscribers.logger")
    @patch("modules.activities.activity_streams.subscribers.core_database")
    @patch("modules.activities.activity_streams.subscribers.activity_streams_service")
    @patch("modules.activities.activity_streams.subscribers.platform_runtime")
    def test_runs_backfill_when_acquired(self, mock_runtime, mock_service, mock_db, mock_logger):
        from modules.activities.activity_streams.subscribers import run_missing_hr_zone_backfill

        lock_cm = MagicMock()
        lock_cm.__enter__.return_value = True
        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value = lock_cm
        mock_service.backfill_missing_hr_zones.return_value = 3

        run_missing_hr_zone_backfill()

        mock_service.backfill_missing_hr_zones.assert_called_once()
