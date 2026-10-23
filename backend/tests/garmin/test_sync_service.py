"""Tests for queueing Garmin Connect gear and health syncs."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.events as garmin_events
import modules.garmin.subscribers as garmin_subscribers
import modules.garmin.sync_service as garmin_sync_service

DAY = date(2026, 1, 1)


@pytest.fixture
def local():
    with (
        patch.object(garmin_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=False)),
        patch.object(garmin_sync_service, "_SYNC_EXECUTOR") as executor,
    ):
        yield executor


@pytest.fixture
def durable():
    with (
        patch.object(garmin_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=True)),
        patch.object(garmin_sync_service.garmin_event_publishers, "publish_sync_requested") as publish,
        patch.object(garmin_sync_service, "_SYNC_EXECUTOR") as executor,
    ):
        yield publish, executor


def test_a_gear_sync_goes_to_the_pool_without_durable_jobs(local):
    garmin_sync_service.request_gear_sync(1, MagicMock())

    local.submit.assert_called_once()
    assert local.submit.call_args.args[2].kind == garmin_constants.SyncKind.GEAR


def test_a_health_sync_is_published_for_a_worker_with_durable_jobs(durable):
    publish, executor = durable
    db = MagicMock()

    garmin_sync_service.request_health_sync(1, DAY, DAY, db)

    publish.assert_called_once_with(1, garmin_constants.SyncKind.HEALTH, DAY, DAY, db, commit=db.commit)
    executor.submit.assert_not_called()


def test_a_reversed_range_is_refused_and_nothing_is_queued(local):
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, date(2026, 1, 2), DAY, MagicMock())

    local.submit.assert_not_called()


def test_a_range_beyond_the_cap_is_refused_and_nothing_is_queued(local):
    end = date(2026, 3, 1)

    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, DAY, end, MagicMock())

    local.submit.assert_not_called()


def test_the_longest_allowed_range_is_accepted(local):
    last = date(2026, 1, garmin_constants.MAX_HEALTH_RANGE_DAYS)

    garmin_sync_service.request_health_sync(1, DAY, last, MagicMock())

    local.submit.assert_called_once()


def test_running_a_queued_sync_dispatches_by_kind():
    with (
        patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear") as gear,
        patch.object(garmin_sync_service.garmin_health_service, "sync_health_for_dates") as health,
    ):
        garmin_sync_service.run_sync(garmin_events.SyncRequestedPayload(user_id=1, kind=garmin_constants.SyncKind.GEAR))
        garmin_sync_service.run_sync(
            garmin_events.SyncRequestedPayload(
                user_id=2, kind=garmin_constants.SyncKind.HEALTH, start_date=DAY, end_date=DAY
            )
        )

    gear.assert_called_once_with(1)
    health.assert_called_once_with(DAY, DAY, 2)


def test_the_durable_handler_runs_the_event_payload():
    event = MagicMock()
    payload = garmin_events.SyncRequestedPayload(user_id=1, kind=garmin_constants.SyncKind.GEAR)
    with (
        patch.object(garmin_subscribers.platform_event_versioning, "parse_payload", return_value=payload),
        patch.object(garmin_subscribers.garmin_sync_service, "run_sync") as run,
    ):
        garmin_subscribers.process_sync_requested_for_event(event)

    run.assert_called_once_with(payload)
