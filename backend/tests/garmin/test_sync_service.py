"""Tests for queueing Garmin Connect gear and health syncs."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.events as garmin_events
import modules.garmin.subscribers as garmin_subscribers
import modules.garmin.sync_service as garmin_sync_service
import modules.garmin.sync_state_store as garmin_sync_state_store

DAY = date(2026, 1, 1)
Kind = garmin_constants.SyncKind
Status = garmin_constants.SyncStatus


@pytest.fixture
def states():
    return garmin_sync_state_store.GarminSyncStateStore(state=MemoryState())


@pytest.fixture(autouse=True)
def fresh_local_slots(monkeypatch):
    import threading

    monkeypatch.setattr(
        garmin_sync_service, "_local_slots", threading.BoundedSemaphore(garmin_constants.MAX_PENDING_LOCAL_SYNCS)
    )


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


def test_a_gear_sync_goes_to_the_pool_without_durable_jobs(local, states):
    result = garmin_sync_service.request_gear_sync(1, states, MagicMock())

    local.submit.assert_called_once()
    assert local.submit.call_args.args[2].kind == Kind.GEAR
    assert result.status == Status.QUEUED
    assert states.get(1, Kind.GEAR).status == Status.QUEUED


def test_a_health_sync_is_published_for_a_worker_with_durable_jobs(durable, states):
    publish, executor = durable
    db = MagicMock()

    garmin_sync_service.request_health_sync(1, DAY, DAY, states, db)

    publish.assert_called_once_with(
        1, Kind.HEALTH, DAY, DAY, db, commit=db.commit, source=garmin_constants.SYNC_SOURCE_API
    )
    executor.submit.assert_not_called()


def test_a_second_sync_of_a_kind_while_one_is_pending_is_a_conflict(local, states):
    garmin_sync_service.request_gear_sync(1, states, MagicMock())

    with pytest.raises(core_exceptions.ConflictError):
        garmin_sync_service.request_gear_sync(1, states, MagicMock())

    local.submit.assert_called_once()


def test_other_kinds_and_other_users_are_not_blocked(local, states):
    garmin_sync_service.request_gear_sync(1, states, MagicMock())

    garmin_sync_service.request_health_sync(1, DAY, DAY, states, MagicMock())
    garmin_sync_service.request_gear_sync(2, states, MagicMock())

    assert local.submit.call_count == 3


def test_a_sync_that_cannot_be_queued_does_not_block_a_retry(local, states):
    local.submit.side_effect = RuntimeError("shut down")
    with pytest.raises(RuntimeError):
        garmin_sync_service.request_gear_sync(1, states, MagicMock())
    local.submit.side_effect = None

    garmin_sync_service.request_gear_sync(1, states, MagicMock())

    assert states.get(1, Kind.GEAR).status == Status.QUEUED


def test_the_pool_refuses_syncs_beyond_its_limit(local, states, monkeypatch):
    import threading

    monkeypatch.setattr(garmin_sync_service, "_local_slots", threading.BoundedSemaphore(1))
    garmin_sync_service.request_gear_sync(1, states, MagicMock())

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        garmin_sync_service.request_gear_sync(2, states, MagicMock())

    assert states.get(2, Kind.GEAR).status == Status.FAILED


def test_a_reversed_range_is_refused_and_nothing_is_queued(local, states):
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, date(2026, 1, 2), DAY, states, MagicMock())

    local.submit.assert_not_called()


def test_a_range_beyond_the_cap_is_refused_and_nothing_is_queued(local, states):
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_health_sync(1, DAY, date(2026, 3, 1), states, MagicMock())

    local.submit.assert_not_called()


def test_the_longest_allowed_range_is_accepted(local, states):
    last = date(2026, 1, garmin_constants.MAX_HEALTH_RANGE_DAYS)

    garmin_sync_service.request_health_sync(1, DAY, last, states, MagicMock())

    local.submit.assert_called_once()


def test_an_activities_range_is_not_capped():
    with patch.object(garmin_sync_service.activity_ingestion_integration, "request_provider_sync") as request:
        garmin_sync_service.request_activities_sync(1, date(2010, 1, 1), DAY, MagicMock(), MagicMock())

    request.assert_called_once()


def test_a_reversed_activities_range_is_refused():
    with pytest.raises(core_exceptions.InvalidInputError):
        garmin_sync_service.request_activities_sync(1, date(2026, 1, 2), DAY, MagicMock(), MagicMock())


def test_an_unrecorded_sync_is_not_found(states):
    with pytest.raises(core_exceptions.NotFoundError):
        garmin_sync_service.get_sync_status(1, Kind.GEAR, states)


class TestRunSync:
    def test_it_dispatches_by_kind_and_records_the_outcome(self, states):
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear") as gear,
            patch.object(garmin_sync_service.garmin_health_service, "sync_health_for_dates") as health,
        ):
            garmin_sync_service.run_sync(garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states)
            garmin_sync_service.run_sync(
                garmin_events.SyncRequestedPayload(user_id=2, kind=Kind.HEALTH, start_date=DAY, end_date=DAY), states
            )

        gear.assert_called_once_with(1)
        health.assert_called_once_with(DAY, DAY, 2)
        assert states.get(1, Kind.GEAR).status == Status.COMPLETED
        assert states.get(2, Kind.HEALTH).status == Status.COMPLETED

    def test_without_a_worker_a_failure_is_recorded_released_and_raised(self, local, states):
        states.begin(1, Kind.GEAR)
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            garmin_sync_service.run_sync(garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states)

        assert states.get(1, Kind.GEAR).status == Status.FAILED
        assert states.begin(1, Kind.GEAR) is True

    def test_with_a_worker_a_failure_stays_queued_and_claimed_for_its_retry(self, durable, states):
        states.begin(1, Kind.GEAR)
        with (
            patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            garmin_sync_service.run_sync(garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states)

        assert states.get(1, Kind.GEAR).status == Status.QUEUED
        assert states.begin(1, Kind.GEAR) is False

    def test_a_sync_that_did_not_run_is_recorded_as_failed_without_a_retry(self, states):
        states.begin(1, Kind.GEAR)
        with patch.object(garmin_sync_service.garmin_gear_service, "get_user_gear", return_value=False):
            garmin_sync_service.run_sync(garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR), states)

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

    def test_with_durable_jobs_each_linked_user_is_queued_for_a_worker(self, durable, states):
        publish, _ = durable
        with (
            patch.object(
                garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], [5], []]
            ) as listing,
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        assert [call.args[0] for call in publish.call_args_list] == [1, 2, 5]
        assert [call.args[0] for call in listing.call_args_list] == [0, 2, 5]

    def test_a_user_with_a_pending_sync_is_skipped(self, durable, states):
        publish, _ = durable
        states.begin(1, Kind.HEALTH)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        assert [call.args[0] for call in publish.call_args_list] == [2]

    def test_without_durable_jobs_each_user_goes_to_the_pool_not_the_scheduler_thread(self, local, states):
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
            patch.object(garmin_sync_service, "run_sync") as run,
        ):
            garmin_sync_service.sync_recent_health(states)

        run.assert_not_called()
        assert local.submit.call_count == 2
        assert states.get(1, Kind.HEALTH).status == Status.QUEUED
        assert states.get(2, Kind.HEALTH).status == Status.QUEUED

    def test_a_pool_that_stays_full_ends_the_pass(self, local, states, monkeypatch):
        import threading

        full = threading.BoundedSemaphore(1)
        full.acquire()
        monkeypatch.setattr(garmin_sync_service, "_local_slots", full)
        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 0.01)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1, 2], []]) as listing,
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        local.submit.assert_not_called()
        assert listing.call_count == 1
        assert states.begin(1, Kind.HEALTH) is True

    def test_a_user_waits_for_a_slot_to_free_instead_of_being_skipped(self, local, states, monkeypatch):
        import threading

        slots = threading.BoundedSemaphore(1)
        slots.acquire()
        monkeypatch.setattr(garmin_sync_service, "_local_slots", slots)
        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 5)
        threading.Timer(0.05, slots.release).start()
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        assert local.submit.call_count == 1
        assert states.get(1, Kind.HEALTH).status == Status.QUEUED

    def test_the_window_is_the_users_local_yesterday_and_today(self, durable, states, local_today):
        publish, _ = durable
        local_today.return_value = date(2026, 3, 10)
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        assert publish.call_args.args[2:4] == (date(2026, 3, 9), date(2026, 3, 10))

    def test_the_event_names_the_scheduler_as_its_source(self, durable, states):
        publish, _ = durable
        with (
            patch.object(garmin_sync_service.garmin_service, "linked_user_ids", side_effect=[[1], []]),
            patch.object(garmin_sync_service.core_database, "SessionLocal"),
        ):
            garmin_sync_service.sync_recent_health(states)

        assert publish.call_args.kwargs["source"] == garmin_constants.SYNC_SOURCE_SCHEDULER

    def test_a_request_names_the_api_as_its_source(self, durable, states):
        publish, _ = durable

        garmin_sync_service.request_gear_sync(1, states, MagicMock())

        assert publish.call_args.kwargs["source"] == garmin_constants.SYNC_SOURCE_API


def test_the_durable_handler_runs_the_event_payload(states):
    event = MagicMock()
    payload = garmin_events.SyncRequestedPayload(user_id=1, kind=Kind.GEAR)
    with (
        patch.object(garmin_subscribers.platform_event_versioning, "parse_payload", return_value=payload),
        patch.object(garmin_subscribers.garmin_sync_state_store, "GarminSyncStateStore", return_value=states),
        patch.object(garmin_subscribers.platform_runtime, "get_state"),
        patch.object(garmin_subscribers.garmin_sync_service, "run_sync") as run,
    ):
        garmin_subscribers.process_sync_requested_for_event(event)

    run.assert_called_once_with(payload, states)
