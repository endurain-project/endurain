"""Queued Strava gear syncs, unlinks and activity ranges run off the request, once per user, and record their outcome."""

from datetime import date, timedelta
from unittest.mock import ANY, MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import core.sync_runner as core_sync_runner
import modules.strava.constants as strava_constants
import modules.strava.events as strava_events
import modules.strava.integration_service as strava_integration
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store
from tests._helpers.auth import MOCK_USER_ID

GEAR = strava_constants.SyncKind.GEAR
UNLINK = strava_constants.SyncKind.UNLINK
Status = strava_constants.SyncStatus


@pytest.fixture
def states():
    return strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())


@pytest.fixture
def rate_limits():
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


def _payload(kind=GEAR, user_id=MOCK_USER_ID):
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
            status = strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, db)

        assert (status.kind, status.status) == ("strava_gear", Status.QUEUED)
        publish.assert_called_once()
        assert publish.call_args.args[:2] == (MOCK_USER_ID, GEAR)
        pool.submit.assert_not_called()

    def test_without_durable_jobs_the_sync_goes_to_the_bounded_pool_not_the_request(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool") as pool:
            status = strava_sync_service.request_unlink(MOCK_USER_ID, states, rate_limits, MagicMock())

        assert (status.kind, status.status) == ("strava_unlink", Status.QUEUED)
        submitted = pool.submit.call_args.args
        assert submitted[0] is strava_sync_service.run_sync
        assert submitted[1].kind == UNLINK

    def test_a_second_request_while_one_is_pending_is_a_conflict(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool"):
            strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, MagicMock())
            with pytest.raises(core_exceptions.JobAlreadyRunningError):
                strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, MagicMock())

    def test_gear_and_unlink_do_not_block_each_other(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool"):
            strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, MagicMock())
            strava_sync_service.request_unlink(MOCK_USER_ID, states, rate_limits, MagicMock())

    def test_a_sync_that_could_not_be_queued_frees_the_user_to_retry(self, states, rate_limits):
        with _settings(False), patch.object(strava_sync_service, "_sync_pool") as pool:
            pool.submit.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, MagicMock())

            assert states.get(MOCK_USER_ID, GEAR).status == Status.FAILED
            pool.submit.side_effect = None
            strava_sync_service.request_gear_sync(MOCK_USER_ID, states, rate_limits, MagicMock())


class TestRunSync:
    def test_a_gear_sync_runs_and_completes(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=True) as run:
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        run.assert_called_once_with(MOCK_USER_ID, rate_limits)
        assert states.get(MOCK_USER_ID, GEAR).status == Status.SUCCEEDED

    def test_a_completed_gear_sync_tells_the_browser_to_refetch_gears(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with (
            patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=True),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        assert [call.args for call in push.call_args_list] == [
            (MOCK_USER_ID, {"message": "JOB_STATUS_CHANGED", "job_id": ANY, "kind": "strava_gear"}),
            (MOCK_USER_ID, {"message": "GEARS_CHANGED"}),
        ]

    def test_a_failed_gear_sync_announces_its_job_but_not_a_gear_change(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with (
            patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=False),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        push.assert_called_once_with(
            MOCK_USER_ID, {"message": "JOB_STATUS_CHANGED", "job_id": ANY, "kind": "strava_gear"}
        )

    def test_a_finished_unlink_announces_its_job_and_no_gear_change(self, states, rate_limits):
        states.begin(MOCK_USER_ID, UNLINK, conflict="busy")
        with (
            patch.object(strava_sync_service.strava_service, "unlink_account", return_value=True),
            patch.object(strava_sync_service.websocket_integration, "push_to_user") as push,
        ):
            strava_sync_service.run_sync(_payload(UNLINK), states, rate_limits)

        push.assert_called_once_with(
            MOCK_USER_ID, {"message": "JOB_STATUS_CHANGED", "job_id": ANY, "kind": "strava_unlink"}
        )

    def test_an_unlink_runs_and_completes_even_when_strava_was_not_linked(self, states, rate_limits):
        states.begin(MOCK_USER_ID, UNLINK, conflict="busy")
        with patch.object(strava_sync_service.strava_service, "unlink_account", return_value=False) as run:
            strava_sync_service.run_sync(_payload(UNLINK), states, rate_limits)

        run.assert_called_once_with(MOCK_USER_ID)
        assert states.get(MOCK_USER_ID, UNLINK).status == Status.SUCCEEDED

    def test_a_link_is_never_run_as_a_sync_job_and_leaves_the_link_state_alone(self, states, rate_limits):
        link = strava_constants.SyncKind.LINK
        states.begin(MOCK_USER_ID, link, conflict="busy")

        with patch.object(strava_sync_service.strava_service, "unlink_account") as unlink, pytest.raises(ValueError):
            strava_sync_service.run_sync(_payload(link), states, rate_limits)

        unlink.assert_not_called()
        assert states.get(MOCK_USER_ID, link).status == Status.QUEUED

    def test_a_gear_sync_for_an_unlinked_account_is_recorded_as_failed(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with patch.object(strava_sync_service.strava_gear_service, "get_user_gear", return_value=False):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.FAILED

    def test_a_rate_limit_fails_the_sync_without_raising_so_nothing_retries_into_it(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with patch.object(
            strava_sync_service.strava_gear_service,
            "get_user_gear",
            side_effect=core_exceptions.TooManyRequestsError("slow down"),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=True)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.FAILED

    def test_a_failure_a_worker_will_retry_keeps_the_claim_held(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with (
            patch.object(
                strava_sync_service.strava_gear_service, "get_user_gear", side_effect=RuntimeError("transient")
            ),
            pytest.raises(RuntimeError),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=True)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(MOCK_USER_ID, GEAR, conflict="busy")

    def test_a_last_failure_is_recorded_and_frees_the_claim(self, states, rate_limits):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        with (
            patch.object(
                strava_sync_service.strava_gear_service, "get_user_gear", side_effect=RuntimeError("permanent")
            ),
            pytest.raises(RuntimeError),
        ):
            strava_sync_service.run_sync(_payload(GEAR), states, rate_limits, will_retry=False)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.FAILED
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")


class TestDeadLetter:
    def test_a_pending_sync_is_closed_so_the_user_can_queue_another(self, states):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")

        strava_sync_service.close_dead_lettered_sync(_payload(GEAR), states)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.FAILED
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")

    def test_a_finished_sync_is_left_as_it_is(self, states):
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        states.set_status(MOCK_USER_ID, GEAR, Status.SUCCEEDED)

        strava_sync_service.close_dead_lettered_sync(_payload(GEAR), states)

        assert states.get(MOCK_USER_ID, GEAR).status == Status.SUCCEEDED


class TestReadSyncJob:
    def test_the_current_job_reads_with_its_id_and_kind(self, states):
        job = states.begin(MOCK_USER_ID, GEAR, conflict="busy")

        read = strava_integration.read_sync_job(job, platform_runtime.get_state())

        assert (read.id, read.kind, read.status) == (job.id, "strava_gear", Status.QUEUED)

    def test_a_finished_job_reads_with_its_outcome(self, states):
        job = states.begin(MOCK_USER_ID, UNLINK, conflict="busy")
        states.set_status(MOCK_USER_ID, UNLINK, Status.SUCCEEDED)

        read = strava_integration.read_sync_job(job, platform_runtime.get_state())

        assert (read.kind, read.status) == ("strava_unlink", Status.SUCCEEDED)
        assert read.finished_at is not None

    def test_a_job_replaced_by_a_later_sync_of_its_subject_reads_as_none(self, states):
        earlier = states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        states.set_status(MOCK_USER_ID, GEAR, Status.SUCCEEDED)
        states.begin(MOCK_USER_ID, GEAR, conflict="busy")

        assert strava_integration.read_sync_job(earlier, platform_runtime.get_state()) is None

    def test_an_expired_job_reads_as_none(self, states):
        job = states.begin(MOCK_USER_ID, GEAR, conflict="busy")
        states.discard(MOCK_USER_ID, GEAR)

        assert strava_integration.read_sync_job(job, platform_runtime.get_state()) is None


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
