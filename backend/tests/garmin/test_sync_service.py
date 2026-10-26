"""Tests for queueing Garmin Connect gear and health syncs."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.events as garmin_events
import modules.garmin.subscribers as garmin_subscribers
import modules.garmin.sync_service as garmin_sync_service
import modules.garmin.sync_state_store as garmin_sync_state_store
from tests._helpers import garmin as garmin_helpers

DAY = date(2026, 1, 1)
Kind = garmin_constants.SyncKind
Status = garmin_constants.SyncStatus


@pytest.fixture(autouse=True)
def users_today():
    with patch.object(garmin_sync_service.users_integration, "local_today", return_value=DAY) as today:
        yield today


@pytest.fixture
def rate_limits():
    return garmin_helpers.rate_limits()


@pytest.fixture
def states():
    return garmin_sync_state_store.GarminSyncStateStore(state=MemoryState())


@pytest.fixture
def local():
    with (
        patch.object(garmin_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=False)),
        patch.object(garmin_sync_service, "_sync_pool") as executor,
    ):
        yield executor


@pytest.fixture
def durable():
    with (
        patch.object(garmin_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=True)),
        patch.object(garmin_sync_service.garmin_event_publishers, "publish_sync_requested") as publish,
        patch.object(garmin_sync_service, "_sync_pool") as executor,
    ):
        yield publish, executor


def test_a_gear_sync_goes_to_the_pool_without_durable_jobs(rate_limits, local, states):
    result = garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

    local.submit.assert_called_once()
    assert local.submit.call_args.args[1].kind == Kind.GEAR
    assert result.status == Status.QUEUED
    assert states.get(1, Kind.GEAR).status == Status.QUEUED


def test_a_health_sync_is_published_for_a_worker_with_durable_jobs(rate_limits, durable, states):
    publish, executor = durable
    db = MagicMock()

    garmin_sync_service.request_health_sync(1, DAY, DAY, states, rate_limits, db)

    publish.assert_called_once_with(
        1, Kind.HEALTH, DAY, DAY, db, commit=db.commit, source=garmin_constants.SYNC_SOURCE_API
    )
    executor.submit.assert_not_called()


def test_a_second_sync_of_a_kind_while_one_is_pending_is_a_conflict(rate_limits, local, states):
    garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

    with pytest.raises(core_exceptions.ConflictError):
        garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

    local.submit.assert_called_once()


def test_other_kinds_and_other_users_are_not_blocked(rate_limits, local, states):
    garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

    garmin_sync_service.request_health_sync(1, DAY, DAY, states, rate_limits, MagicMock())
    garmin_sync_service.request_gear_sync(2, states, rate_limits, MagicMock())

    assert local.submit.call_count == 3


def test_a_sync_that_cannot_be_queued_does_not_block_a_retry(rate_limits, local, states):
    local.submit.side_effect = RuntimeError("shut down")
    with pytest.raises(RuntimeError):
        garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())
    local.submit.side_effect = None

    garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

    assert states.get(1, Kind.GEAR).status == Status.QUEUED


@pytest.fixture
def full_pool(blocked_pool, monkeypatch):
    """Replace the sync pool with one already holding its only job, which stays until the test releases it."""
    pool = blocked_pool(1)
    monkeypatch.setattr(garmin_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=False))
    monkeypatch.setattr(garmin_sync_service, "run_sync", lambda *args: blocked_pool.release.wait(5))
    monkeypatch.setattr(garmin_sync_service, "_sync_pool", pool)
    pool.submit(blocked_pool.release.wait, 5)
    return blocked_pool.release


def test_the_pool_refuses_syncs_beyond_its_limit(rate_limits, states, full_pool):
    with pytest.raises(core_exceptions.ServiceUnavailableError):
        garmin_sync_service.request_gear_sync(2, states, rate_limits, MagicMock())

    assert states.get(2, Kind.GEAR).status == Status.FAILED


def test_a_reversed_range_is_refused_and_nothing_is_queued(rate_limits, local, states):
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, date(2026, 1, 2), DAY, states, rate_limits, MagicMock())

    local.submit.assert_not_called()


def test_a_range_beyond_the_cap_is_refused_and_nothing_is_queued(rate_limits, local, states):
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, DAY, date(2026, 3, 1), states, rate_limits, MagicMock())

    local.submit.assert_not_called()


def test_the_longest_allowed_range_is_accepted(rate_limits, local, states, users_today):
    last = date(2026, 1, garmin_constants.MAX_HEALTH_RANGE_DAYS)
    users_today.return_value = last

    garmin_sync_service.request_health_sync(1, DAY, last, states, rate_limits, MagicMock())

    local.submit.assert_called_once()


def test_an_activities_range_beyond_the_cap_is_refused():
    with (
        patch.object(garmin_sync_service.activity_ingestion_integration, "request_provider_sync") as request,
        pytest.raises(core_exceptions.InvalidInputError, match="must not exceed"),
    ):
        garmin_sync_service.request_activities_sync(1, date(2010, 1, 1), DAY, MagicMock(), MagicMock())

    request.assert_not_called()


def test_the_longest_allowed_activities_range_is_accepted():
    first = DAY - timedelta(days=garmin_constants.MAX_ACTIVITIES_RANGE_DAYS - 1)
    with patch.object(garmin_sync_service.activity_ingestion_integration, "request_provider_sync") as request:
        garmin_sync_service.request_activities_sync(1, first, DAY, MagicMock(), MagicMock())

    request.assert_called_once()


def test_a_range_ending_after_the_users_today_is_refused(rate_limits, local, states):
    tomorrow = DAY + timedelta(days=1)
    with (
        patch.object(garmin_sync_service.activity_ingestion_integration, "request_provider_sync") as request,
        pytest.raises(core_exceptions.InvalidInputError, match="future"),
    ):
        garmin_sync_service.request_activities_sync(1, DAY, tomorrow, MagicMock(), MagicMock())
    with pytest.raises(core_exceptions.InvalidInputError, match="future"):
        garmin_sync_service.request_health_sync(1, DAY, tomorrow, states, rate_limits, MagicMock())

    request.assert_not_called()
    local.submit.assert_not_called()


def test_a_reversed_activities_range_is_refused():
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_activities_sync(1, date(2026, 1, 2), DAY, MagicMock(), MagicMock())


def test_an_unrecorded_sync_is_not_found(states):
    with pytest.raises(core_exceptions.NotFoundError):
        garmin_sync_service.get_sync_status(1, Kind.GEAR, states)


class TestRunSync:
    def test_it_dispatches_by_kind_and_records_the_outcome(self, rate_limits, states):
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear") as gear,
            patch.object(garmin_sync_service.garmin_health_service, "sync_health_for_dates") as health,
        ):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=2, kind=Kind.HEALTH, start_date=DAY, end_date=DAY),
                states,
                rate_limits,
            )

        gear.assert_called_once_with(1, rate_limits)
        health.assert_called_once_with(DAY, DAY, 2, rate_limits)
        assert states.get(1, Kind.GEAR).status == Status.COMPLETED
        assert states.get(2, Kind.HEALTH).status == Status.COMPLETED

    def test_a_completed_sync_tells_the_browser_what_to_refetch(self, rate_limits, states):
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", return_value=True),
            patch.object(garmin_sync_service.garmin_health_service, "sync_health_for_dates", return_value=True),
            patch.object(garmin_sync_service.websocket_integration, "push_to_user") as push,
        ):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=2, kind=Kind.HEALTH, start_date=DAY, end_date=DAY),
                states,
                rate_limits,
            )

        assert [call.args for call in push.call_args_list] == [
            (1, {"message": "GEARS_CHANGED"}),
            (2, {"message": "HEALTH_CHANGED"}),
        ]

    def test_a_sync_that_did_not_complete_pushes_nothing(self, rate_limits, states):
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", return_value=False),
            patch.object(garmin_sync_service.websocket_integration, "push_to_user") as push,
        ):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )

        push.assert_not_called()

    def test_a_failure_nothing_retries_is_recorded_released_and_raised(self, rate_limits, states):
        states.begin(1, Kind.GEAR)
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )

        assert states.get(1, Kind.GEAR).status == Status.FAILED
        assert states.begin(1, Kind.GEAR) is True

    def test_a_failure_with_attempts_left_stays_queued_and_claimed_for_its_retry(self, rate_limits, states):
        states.begin(1, Kind.GEAR)
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits, will_retry=True
            )

        assert states.get(1, Kind.GEAR).status == Status.QUEUED
        assert states.begin(1, Kind.GEAR) is False

    def test_a_rate_limited_sync_is_failed_without_a_retry(self, rate_limits, durable, states):
        states.begin(1, Kind.GEAR)
        error = garmin_sync_service.garminconnect.GarminConnectTooManyRequestsError("429")
        with patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=error):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )

        assert states.get(1, Kind.GEAR).status == Status.FAILED
        assert states.begin(1, Kind.GEAR) is True

    def test_a_rate_limited_sync_records_the_limit_for_every_replica(self, durable, states, rate_limits):
        states.begin(1, Kind.GEAR)
        error = garmin_sync_service.garminconnect.GarminConnectTooManyRequestsError("429")
        with patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=error):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )

        assert rate_limits.rate_limited_until(1) is not None

    def test_a_sync_refused_by_an_active_limit_is_failed_without_a_retry(self, durable, states, rate_limits):
        states.begin(1, Kind.GEAR)
        error = core_exceptions.TooManyRequestsError("slow down")
        with patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=error):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits, will_retry=True
            )

        assert states.get(1, Kind.GEAR).status == Status.FAILED
        assert states.begin(1, Kind.GEAR) is True

    def test_a_sync_that_did_not_run_is_recorded_as_failed_without_a_retry(self, rate_limits, states):
        states.begin(1, Kind.GEAR)
        with patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", return_value=False):
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states, rate_limits
            )

        assert states.get(1, Kind.GEAR).status == Status.FAILED
        assert states.begin(1, Kind.GEAR) is True

    def test_a_health_payload_needs_a_date_range(self):
        with pytest.raises(ValueError):
            garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.HEALTH)


class TestRecentHealth:
    @pytest.fixture(autouse=True)
    def local_today(self):
        with patch.object(garmin_sync_service.users_integration, "local_today", return_value=DAY) as today:
            yield today

    def test_with_durable_jobs_each_linked_user_is_queued_for_a_worker(self, rate_limits, durable, states):
        publish, _ = durable
        with (
            patch.object(
                garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], [5], []]
            ) as listing,
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert [call.args[0] for call in publish.call_args_list] == [1, 2, 5]
        assert [call.args[0] for call in listing.call_args_list] == [0, 2, 5]

    def test_a_user_with_a_pending_sync_is_skipped(self, rate_limits, durable, states):
        publish, _ = durable
        states.begin(1, Kind.HEALTH)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert [call.args[0] for call in publish.call_args_list] == [2]

    def test_without_durable_jobs_each_user_goes_to_the_pool_not_the_scheduler_thread(self, rate_limits, local, states):
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
            patch.object(garmin_sync_service, "run_sync") as run,
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        run.assert_not_called()
        assert local.submit.call_count == 2
        assert states.get(1, Kind.HEALTH).status == Status.QUEUED
        assert states.get(2, Kind.HEALTH).status == Status.QUEUED

    def test_a_pool_that_stays_full_ends_the_pass(self, rate_limits, full_pool, states, monkeypatch):
        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 0.01)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]) as listing,
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert listing.call_count == 1
        assert states.begin(1, Kind.HEALTH) is True

    def test_a_user_waits_for_a_slot_to_free_instead_of_being_skipped(
        self, rate_limits, full_pool, states, monkeypatch
    ):
        import threading

        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 5)
        threading.Timer(0.05, full_pool.set).start()
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert states.get(1, Kind.HEALTH).status == Status.QUEUED

    def test_the_window_is_the_users_local_yesterday_and_today(self, rate_limits, durable, states, local_today):
        publish, _ = durable
        local_today.return_value = date(2026, 3, 10)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert publish.call_args.args[2:4] == (date(2026, 3, 9), date(2026, 3, 10))

    def test_the_event_names_the_scheduler_as_its_source(self, rate_limits, durable, states):
        publish, _ = durable
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states, rate_limits)

        assert publish.call_args.kwargs["source"] == garmin_constants.SYNC_SOURCE_SCHEDULER

    def test_a_request_names_the_api_as_its_source(self, rate_limits, durable, states):
        publish, _ = durable

        garmin_sync_service.request_gear_sync(1, states, rate_limits, MagicMock())

        assert publish.call_args.kwargs["source"] == garmin_constants.SYNC_SOURCE_API


def _sync_event(retry_count: int = 1, max_attempts: int | None = 3) -> Event:
    return Event(
        event_id="evt-1",
        event_type=garmin_events.GARMIN_SYNC_REQUESTED,
        source="test",
        timestamp="2026-10-31T00:00:00+00:00",
        payload={"user_id": 1, "kind": "gear"},
        retry_count=retry_count,
        max_attempts=max_attempts,
    )


@pytest.mark.parametrize(("retry_count", "will_retry"), [(1, True), (2, True), (3, False)])
def test_the_durable_handler_asks_for_a_retry_only_while_attempts_remain(states, rate_limits, retry_count, will_retry):
    payload = garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR)
    with (
        patch.object(garmin_subscribers.garmin_sync_state_store, "GarminSyncStateStore", return_value=states),
        patch.object(garmin_subscribers.garmin_rate_limit_store, "GarminRateLimitStore", return_value=rate_limits),
        patch.object(garmin_subscribers.platform_runtime, "get_state"),
        patch.object(garmin_subscribers.garmin_sync_service, "run_sync") as run,
    ):
        garmin_subscribers.process_sync_requested_for_event(_sync_event(retry_count))

    run.assert_called_once_with(payload, states, rate_limits, will_retry=will_retry)


class TestDeadLetter:
    """A sync the runner gave up on ends as failed, however its last attempt ended."""

    @pytest.fixture
    def stores(self, states):
        with (
            patch.object(garmin_subscribers.garmin_sync_state_store, "GarminSyncStateStore", return_value=states),
            patch.object(garmin_subscribers.platform_runtime, "get_state"),
        ):
            yield states

    @pytest.mark.parametrize("status", [Status.QUEUED, Status.RUNNING])
    def test_a_pending_sync_is_failed_and_its_claim_released(self, stores, status):
        stores.begin(1, Kind.GEAR)
        stores.set_status(1, Kind.GEAR, status)

        garmin_subscribers.on_sync_requested_dead_letter(_sync_event(3), "lease expired")

        assert stores.get(1, Kind.GEAR).status == Status.FAILED
        assert stores.begin(1, Kind.GEAR) is True

    def test_a_sync_that_already_finished_is_left_alone(self, stores):
        stores.begin(1, Kind.GEAR)
        stores.set_status(1, Kind.GEAR, Status.COMPLETED)

        garmin_subscribers.on_sync_requested_dead_letter(_sync_event(3), None)

        assert stores.get(1, Kind.GEAR).status == Status.COMPLETED

    def test_an_expired_state_is_not_resurrected(self, stores):
        garmin_subscribers.on_sync_requested_dead_letter(_sync_event(3), None)

        assert stores.get(1, Kind.GEAR) is None

    def test_the_handler_is_registered_with_the_callback(self):
        registry = JobHandlerRegistry()

        garmin_subscribers.register_durable_handlers(registry)

        assert registry.dead_letter_subscriber_ids() == {garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID}
