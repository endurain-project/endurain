"""Queued Strava gear syncs and unlinks run off the request, once per user, and record their outcome."""

from unittest.mock import MagicMock, patch

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
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
