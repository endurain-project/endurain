"""Queued Strava gear syncs, unlinks and activity ranges run off the request, once per user, and record their outcome."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import core.sync_runner as core_sync_runner
import modules.strava.constants as strava_constants
import modules.strava.events as strava_events
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store

GEAR = strava_constants.SyncKind.GEAR
UNLINK = strava_constants.SyncKind.UNLINK
Status = strava_constants.SyncStatus


@pytest.fixture
def states():
    return strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())


@pytest.fixture
def rate_limits():
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


def _payload(kind=GEAR, user_id=7):
    return strava_events.SyncRequestedPayload(user_id=user_id, kind=kind)


def _settings(jobs_enabled: bool):
    return patch.object(strava_sync_service.core_config, "settings", MagicMock(JOBS_ENABLED=jobs_enabled))


class TestRequest:
    def test_with_durable_jobs_the_event_is_published_and_nothing_runs_inline(self, states, rate_limits):
        db = MagicMock()
        with (
            _settings(True),
            patch.object(strava_sync_service.strava_event_publishers, "publish_sync_requested") as publish,
            patch.object(strava_sync_service, "_sync_pool") as pool,
        ):
            status = strava_sync_service.request_gear_sync(7, states, rate_limits, db)

        assert (status.kind, status.status) == (GEAR, Status.QUEUED)
        publish.assert_called_once()
        assert publish.call_args.args[:2] == (7, GEAR)
        pool.submit.assert_not_called()

    def test_without_durable_jobs_the_sync_goes_to_the_bounded_pool_not_the_request(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool") as pool:
            status = strava_sync_service.request_unlink(7, states, rate_limits, MagicMock())

        assert (status.kind, status.status) == (UNLINK, Status.QUEUED)
        submitted = pool.submit.call_args.args
        assert submitted[0] is strava_sync_service.run_sync
        assert submitted[1].kind == UNLINK

    def test_a_second_request_while_one_is_pending_is_a_conflict(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool"):
            strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())
            with pytest.raises(core_exceptions.ConflictError):
                strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())

    def test_gear_and_unlink_do_not_block_each_other(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool"):
            strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())
            strava_sync_service.request_unlink(7, states, rate_limits, MagicMock())

    def test_a_sync_that_could_not_be_queued_frees_the_user_to_retry(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool") as pool:
            pool.submit.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())

            assert states.get(7, GEAR).status == Status.FAILED
            pool.submit.side_effect = None
            strava_sync_service.request_gear_sync(7, states, rate_limits, MagicMock())


class TestRunSync:
    def test_a_gear_sync_runs_and_completes(self, states, rate_limits):
        states.begin(7, GEAR)
        with patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=True) as run:
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        run.assert_called_once_with(7, rate_limits)
        assert states.get(7, GEAR).status == Status.COMPLETED

    def test_a_completed_gear_sync_tells_the_browser_to_refetch_gears(self, states, rate_limits):
        states.begin(7, GEAR)
        with (
            patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=True),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        push.assert_called_once_with(7, {"message": "GEARS_CHANGED"})

    def test_a_failed_gear_sync_pushes_nothing(self, states, rate_limits):
        states.begin(7, GEAR)
        with (
            patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=False),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        push.assert_not_called()

    def test_a_finished_unlink_announces_its_job_and_no_gear_change(self, states, rate_limits):
        states.begin(7, UNLINK)
        with (
            patch.object(strava_sync_service.strava_service, "unlink_account", return_value=True),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(UNLINK), states, rate_limits)

        push.assert_called_once_with(7, {"message": "JOB_STATUS_CHANGED", "job": "strava:unlink"})

    def test_an_unlink_runs_and_completes_even_when_strava_was_not_linked(self, states, rate_limits):
        states.begin(7, UNLINK)
        with patch.object(strava_sync_service.strava_service, "unlink_account", return_value=False) as run:
            strava_sync_service.run_sync(_payload(UNLINK), states, rate_limits)

        run.assert_called_once_with(7)
        assert states.get(7, UNLINK).status == Status.COMPLETED

    def test_a_link_is_never_run_as_a_sync_job_and_leaves_the_link_state_alone(self, states, rate_limits):
        link = strava_constants.SyncKind.LINK
        states.begin(7, link)

        with patch.object(strava_sync_service.strava_service, "unlink_account") as unlink, pytest.raises(ValueError):
            strava_sync_service.run_sync(_payload(link), states, rate_limits)

        unlink.assert_not_called()
        assert states.get(7, link).status == Status.QUEUED

    def test_a_gear_sync_for_an_unlinked_account_is_recorded_as_failed(self, states, rate_limits):
        states.begin(7, GEAR)
        with patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=False):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        assert states.get(7, GEAR).status == Status.FAILED

    def test_a_rate_limit_fails_the_sync_without_raising_so_nothing_retries_into_it(self, states, rate_limits):
        states.begin(7, GEAR)
        with patch.object(
            strava_sync_service.strava_gear_service,
            "get_user_gear",
            side_effect=core_exceptions.TooManyRequestsError("slow down"),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=True)

        assert states.get(7, GEAR).status == Status.FAILED

    def test_a_failure_a_worker_will_retry_keeps_the_claim_held(self, states, rate_limits):
        states.begin(7, GEAR)
        with (
            patch.object(
                strava_sync_service.strava_gear_service, "get_user_gear", side_effect=RuntimeError("transient")
            ),
            pytest.raises(RuntimeError),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=True)

        assert states.get(7, GEAR).status == Status.QUEUED
        assert states.begin(7, GEAR) is False

    def test_a_last_failure_is_recorded_and_frees_the_claim(self, states, rate_limits):
        states.begin(7, GEAR)
        with (
            patch.object(
                strava_sync_service.strava_gear_service, "get_user_gear", side_effect=RuntimeError("permanent")
            ),
            pytest.raises(RuntimeError),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=False)

        assert states.get(7, GEAR).status == Status.FAILED
        assert states.begin(7, GEAR) is True


class TestDeadLetter:
    def test_a_pending_sync_is_closed_so_the_user_can_queue_another(self, states):
        states.begin(7, GEAR)

        strava_sync_service.close_dead_lettered_sync(_payload(GEAR), states)

        assert states.get(7, GEAR).status == Status.FAILED
        assert states.begin(7, GEAR) is True

    def test_a_finished_sync_is_left_as_it_is(self, states):
        states.begin(7, GEAR)
        states.set_status(7, GEAR, Status.COMPLETED)

        strava_sync_service.close_dead_lettered_sync(_payload(GEAR), states)

        assert states.get(7, GEAR).status == Status.COMPLETED


class TestStatus:
    def test_the_recorded_status_is_reported(self, states):
        states.begin(7, GEAR)

        assert strava_sync_service.get_sync_status(7, GEAR, states).status == Status.QUEUED

    def test_an_unknown_sync_is_not_found(self, states):
        with pytest.raises(core_exceptions.NotFoundError):
            strava_sync_service.get_sync_status(7, UNLINK, states)

    def test_users_cannot_see_each_others_syncs(self, states):
        states.begin(7, GEAR)

        with pytest.raises(core_exceptions.NotFoundError):
            strava_sync_service.get_sync_status(8, GEAR, states)


@pytest.fixture(autouse=False)
def _local_today(monkeypatch):
    monkeypatch.setattr(
        strava_sync_service.activity_ingestion_integration.users_integration,
        "local_today",
        lambda _user_id, _db: date(2026, 10, 26),
    )


@pytest.mark.usefixtures("_local_today")
class TestRequestActivitiesSync:
    def test_a_range_ending_in_the_future_is_refused(self):
        with (
            patch.object(
                strava_sync_service.activity_ingestion_integration.activity_ingestion_service, "accept_refresh"
            ) as request,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            strava_sync_service.request_activities_sync(
                1, date(2026, 10, 1), date(2026, 10, 27), MagicMock(), MagicMock()
            )

        request.assert_not_called()

    def test_a_range_ending_before_it_starts_is_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_sync_service.request_activities_sync(1, date(2026, 2, 1), date(2026, 1, 1), MagicMock(), MagicMock())

    def test_a_range_longer_than_the_cap_is_refused(self):
        start = date(2025, 1, 1)
        too_long = start + timedelta(days=core_sync_runner.MAX_ACTIVITIES_RANGE_DAYS)
        with (
            patch.object(
                strava_sync_service.activity_ingestion_integration.activity_ingestion_service, "accept_refresh"
            ) as request,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            strava_sync_service.request_activities_sync(1, start, too_long, MagicMock(), MagicMock())

        request.assert_not_called()

    def test_a_range_at_the_cap_is_queued(self):
        start = date(2025, 1, 1)
        last = start + timedelta(days=core_sync_runner.MAX_ACTIVITIES_RANGE_DAYS - 1)
        with patch.object(
            strava_sync_service.activity_ingestion_integration.activity_ingestion_service,
            "accept_refresh",
            return_value="job",
        ) as request:
            strava_sync_service.request_activities_sync(1, start, last, MagicMock(), MagicMock())

        request.assert_called_once()

    def test_the_whole_last_day_is_requested(self):
        with patch.object(
            strava_sync_service.activity_ingestion_integration.activity_ingestion_service,
            "accept_refresh",
            return_value="job",
        ) as request:
            job = strava_sync_service.request_activities_sync(
                1, date(2026, 1, 1), date(2026, 1, 2), MagicMock(), MagicMock()
            )

        assert job == "job"
        provider, start, end = (request.call_args.kwargs[k] for k in ("provider", "window_start", "window_end"))
        assert provider == "strava"
        assert (start.hour, end.hour, end.minute) == (0, 23, 59)
