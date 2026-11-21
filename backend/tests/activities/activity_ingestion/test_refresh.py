"""A provider refresh pulls a user's linked providers through the real route, pool and pipeline.

The provider is the one thing not ours: a stub registered with ingestion that hands over real GPX files, so everything
after it (the pipeline, the stored activities, the job rows, the pool) is the production code.
"""

import logging
import threading
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.service as ingestion_service
from tests._factories.garmin import activity_gpx
from tests._factories.ingestion import StubProvider, activities_of, all_jobs, read_job, stage_job
from tests._factories.users import make_user
from tests.activities.activity_ingestion.conftest import DrainedPool

_API = core_config.ROOT_PATH
_JOBS = f"{_API}/jobs"
_Kind = ingestion_constants.IngestionJobKind
_ErrorCode = ingestion_constants.IngestionJobErrorCode


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _refresh(user):
    return user.client.post(f"{_API}/activities/refresh")


def _state(user, response) -> dict:
    return user.client.get(f"{_JOBS}/{response.json()['id']}").json()


def _rate_limited(retry_at: datetime | None) -> core_exceptions.TooManyRequestsError:
    return core_exceptions.TooManyRequestsError(
        "Provider rate limit", scope=core_exceptions.TooManyRequestsScope.PROVIDER, retry_at=retry_at
    )


class TestARefreshRequest:
    def test_the_job_is_visible_as_running_while_the_provider_is_being_asked(
        self, me, stub_provider, pool, committed_sessions
    ):
        seen: list[str] = []
        stub_provider.on_fetch = lambda: seen.append(all_jobs(committed_sessions)[0].status)
        stub_provider.link(me.user.id)

        _refresh(me)
        pool.drain()

        assert seen == ["processing"]

    def test_stores_what_the_linked_provider_hands_over_and_records_it_on_the_job(
        self, me, stub_provider, pool, committed_sessions
    ):
        stub_provider.link(me.user.id, activity_gpx(name="Morning Run"))

        response = _refresh(me)
        pool.drain()

        assert response.status_code == 202
        state = _state(me, response)
        assert (state["kind"], state["status"], state["error_code"]) == ("activity_refresh", "succeeded", None)
        (activity,) = activities_of(committed_sessions, me.user.id)
        assert state["activity_ids"] == [str(activity.id)]

    def test_syncs_the_last_day_when_it_names_no_window(self, me, stub_provider, pool):
        stub_provider.link(me.user.id)

        _refresh(me)
        pool.drain()

        ((user_id, start, end),) = stub_provider.calls
        assert user_id == me.user.id
        assert end - start == timedelta(days=1)
        assert abs((end - datetime.now(UTC)).total_seconds()) < 60

    def test_finding_nothing_new_is_a_success(self, me, stub_provider, pool):
        stub_provider.link(me.user.id)

        response = _refresh(me)
        pool.drain()

        state = _state(me, response)
        assert (state["status"], state["activity_ids"]) == ("succeeded", [])

    def test_a_user_who_linked_nothing_gets_an_empty_success(self, me, providers, pool):
        response = _refresh(me)
        pool.drain()

        assert _state(me, response)["status"] == "succeeded"

    def test_only_syncs_the_requesting_users_provider_account(self, me, make_signed_in, stub_provider, pool):
        other = make_signed_in()
        stub_provider.link(me.user.id)
        stub_provider.link(other.user.id, activity_gpx())

        _refresh(me)
        pool.drain()

        assert [user_id for user_id, _start, _end in stub_provider.calls] == [me.user.id]

    def test_tells_the_owner_when_the_sync_finished(self, me, stub_provider, pool, hints):
        stub_provider.link(me.user.id)

        _refresh(me)
        pool.drain()

        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]


class TestAProviderThatIsRateLimited:
    def test_defers_the_job_until_the_limit_clears_instead_of_failing_it(
        self, me, stub_provider, pool, committed_sessions, hints
    ):
        retry_at = datetime.now(UTC) + timedelta(hours=2)
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(retry_at)

        response = _refresh(me)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert row.status == "deferred"
        assert abs((row.retry_after - retry_at).total_seconds()) < 1
        assert (row.error_code, row.completed_at) == (None, None)
        assert _state(me, response)["status"] == "queued"
        assert hints == [], "a deferral is not an outcome, so nobody is told"

    def test_tells_the_client_when_the_deferred_job_runs_again(self, me, stub_provider, pool):
        retry_at = datetime.now(UTC) + timedelta(hours=2)
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(retry_at)

        response = _refresh(me)
        pool.drain()

        assert datetime.fromisoformat(_state(me, response)["retry_after"]) == retry_at

    def test_waits_a_default_while_when_the_limit_has_no_known_end(self, me, stub_provider, pool, committed_sessions):
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(None)

        response = _refresh(me)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        wait = row.retry_after - datetime.now(UTC)
        assert row.status == "deferred"
        assert timedelta(minutes=14) < wait <= timedelta(minutes=15)

    def test_waits_for_the_last_limit_to_clear_when_several_providers_are_limited(
        self, me, stub_provider, pool, committed_sessions
    ):
        early, late = datetime.now(UTC) + timedelta(hours=1), datetime.now(UTC) + timedelta(hours=3)
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(early)
        second = StubProvider("second").register()
        second.link(me.user.id)
        second.failure = _rate_limited(late)

        response = _refresh(me)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert abs((row.retry_after - late).total_seconds()) < 1

    def test_a_real_failure_wins_so_the_job_fails_instead_of_waiting(self, me, stub_provider, pool, committed_sessions):
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(datetime.now(UTC) + timedelta(hours=1))
        broken = StubProvider("broken").register()
        broken.link(me.user.id)
        broken.failure = RuntimeError("provider is down")

        response = _refresh(me)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", _ErrorCode.PROVIDER_UNAVAILABLE.value)

    def test_the_other_providers_are_still_asked(self, me, stub_provider, pool, committed_sessions):
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(datetime.now(UTC) + timedelta(hours=1))
        healthy = StubProvider("healthy").register()
        healthy.link(me.user.id, activity_gpx())

        _refresh(me)
        pool.drain()

        assert len(healthy.calls) == 1
        assert len(activities_of(committed_sessions, me.user.id)) == 1


class TestAProviderThatFails:
    def test_fails_the_job_since_nothing_will_retry_it(self, me, stub_provider, pool, committed_sessions, hints):
        stub_provider.link(me.user.id)
        stub_provider.failure = RuntimeError("provider is down")

        response = _refresh(me)
        pool.drain()

        state = _state(me, response)
        assert (state["status"], state["error_code"]) == ("failed", _ErrorCode.PROVIDER_UNAVAILABLE.value)
        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]

    def test_does_not_stop_the_other_providers(self, me, stub_provider, pool, committed_sessions):
        stub_provider.link(me.user.id)
        stub_provider.failure = RuntimeError("provider is down")
        healthy = StubProvider("healthy").register()
        healthy.link(me.user.id, activity_gpx())

        response = _refresh(me)
        pool.drain()

        assert len(activities_of(committed_sessions, me.user.id)) == 1
        assert _state(me, response)["status"] == "failed"


class TestARangeSyncOfOneProvider:
    def _request(self, db, user_id, start: date, end: date, provider: str = "stub"):
        return ingestion_integration.request_range_sync(
            provider, user_id, start, end, ingestion_integration.platform_runtime.get_active_platform().storage, db
        )

    def test_syncs_only_that_provider_over_the_whole_of_both_days(self, me, stub_provider, pool, committed_sessions):
        other = StubProvider("other").register()
        other.link(me.user.id)
        stub_provider.link(me.user.id)
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        start = yesterday - timedelta(days=3)

        with committed_sessions() as db:
            job = self._request(db, me.user.id, start, yesterday)
        pool.drain()

        row = read_job(committed_sessions, job.id)
        assert (row.kind, row.provider, row.status) == ("refresh", "stub", "completed")
        ((_user, window_start, window_end),) = stub_provider.calls
        assert window_start == datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        assert window_end == datetime.combine(yesterday, datetime.max.time(), tzinfo=UTC)
        assert other.calls == []

    def test_a_provider_missing_from_this_process_fails_the_job_instead_of_completing_it_empty(
        self, me, providers, pool, committed_sessions
    ):
        yesterday = datetime.now(UTC).date() - timedelta(days=1)

        with committed_sessions() as db:
            job = self._request(db, me.user.id, yesterday, yesterday, provider="absent")
        pool.drain()

        assert read_job(committed_sessions, job.id).status == "failed"

    def test_a_range_ending_in_the_future_is_refused_before_a_job_exists(
        self, me, stub_provider, pool, committed_sessions
    ):
        tomorrow = datetime.now(UTC).date() + timedelta(days=2)

        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError):
            self._request(db, me.user.id, tomorrow, tomorrow)

        assert all_jobs(committed_sessions) == []

    def test_a_range_over_the_cap_is_refused_before_a_job_exists(self, me, stub_provider, pool, committed_sessions):
        end = datetime.now(UTC).date() - timedelta(days=1)

        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError):
            self._request(db, me.user.id, end - timedelta(days=400), end)

        assert all_jobs(committed_sessions) == []


class TestTheScheduledFanOut:
    @pytest.fixture
    def users(self, committed_sessions):
        with committed_sessions() as db:
            created = [make_user(db, timezone="UTC") for _ in range(3)]
            db.commit()
        return sorted(created, key=lambda user: user.id)

    def _fan_out(self, storage) -> int:
        return ingestion_service.enqueue_scheduled_refreshes(storage)

    def test_queues_one_job_per_linked_user_and_runs_each(
        self, users, stub_provider, pool, storage, committed_sessions
    ):
        for user in users:
            stub_provider.link(user.id, activity_gpx(name=f"Ride of {user.username}"))

        queued = self._fan_out(storage)
        pool.drain()

        assert queued == 3
        jobs = all_jobs(committed_sessions)
        assert sorted(job.user_id for job in jobs) == [user.id for user in users]
        assert {job.status for job in jobs} == {"completed"}
        assert all(len(activities_of(committed_sessions, user.id)) == 1 for user in users)

    def test_a_user_linked_to_two_providers_gets_one_job(self, users, stub_provider, pool, storage, committed_sessions):
        second = StubProvider("second").register()
        stub_provider.link(users[0].id)
        stub_provider.link(users[1].id)
        second.link(users[1].id)
        second.link(users[2].id)

        queued = self._fan_out(storage)
        pool.drain()

        assert queued == 3
        assert len(all_jobs(committed_sessions)) == 3

    def test_a_user_whose_previous_refresh_has_not_finished_is_skipped(
        self, users, stub_provider, pool, storage, committed_sessions
    ):
        for user in users:
            stub_provider.link(user.id)
        with committed_sessions() as db:
            stage_job(db, users[0].id, kind=_Kind.REFRESH, status="processing")
            stage_job(db, users[1].id, kind=_Kind.REFRESH, status="deferred", retry_after=datetime.now(UTC))
            db.commit()

        queued = self._fan_out(storage)
        pool.drain()

        assert queued == 1
        assert [call[0] for call in stub_provider.calls] == [users[2].id]

    def test_a_fan_out_where_every_linked_user_is_still_busy_queues_nothing(
        self, users, stub_provider, pool, storage, committed_sessions
    ):
        stub_provider.link(users[0].id)
        with committed_sessions() as db:
            stage_job(db, users[0].id, kind=_Kind.REFRESH, status="processing")
            db.commit()

        assert self._fan_out(storage) == 0
        assert stub_provider.calls == []

    def test_pages_through_every_linked_user(self, stub_provider, pool, storage, committed_sessions, monkeypatch):
        monkeypatch.setattr(ingestion_service, "_REFRESH_FANOUT_BATCH_SIZE", 2)
        with committed_sessions() as db:
            created = [make_user(db, timezone="UTC") for _ in range(5)]
            db.commit()
        for user in created:
            stub_provider.link(user.id)

        queued = self._fan_out(storage)
        pool.drain()

        assert queued == 5
        assert {job.user_id for job in all_jobs(committed_sessions)} == {user.id for user in created}

    def test_a_full_pool_is_waited_on_so_every_linked_user_is_refreshed(
        self, stub_provider, committed_sessions, storage, monkeypatch
    ):
        busy = DrainedPool(workers=1, max_pending=3)
        monkeypatch.setattr(ingestion_background, "_pool", busy)
        with committed_sessions() as db:
            created = [make_user(db, timezone="UTC") for _ in range(7)]
            db.commit()
        for user in created:
            stub_provider.link(user.id)

        try:
            queued = self._fan_out(storage)
            busy.drain()
        finally:
            busy.shutdown(wait=True)

        assert queued == 7
        assert {job.status for job in all_jobs(committed_sessions)} == {"completed"}

    def test_a_job_whose_slot_never_comes_is_failed_so_the_user_is_not_blocked(
        self, users, stub_provider, committed_sessions, storage, monkeypatch
    ):
        release = threading.Event()
        stuck = core_local_pool.BoundedPool("stuck", workers=1, max_pending=1)
        monkeypatch.setattr(ingestion_background, "_pool", stuck)
        monkeypatch.setattr(ingestion_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 0.05)
        stuck.submit(release.wait, 10)
        stub_provider.link(users[0].id)

        try:
            self._fan_out(storage)
        finally:
            release.set()
            stuck.shutdown(wait=True)

        (job,) = all_jobs(committed_sessions)
        assert (job.status, job.error_code) == ("failed", _ErrorCode.PROCESSING_FAILED.value)

    def test_nothing_is_queued_when_no_provider_has_a_linked_user(self, providers, pool, storage, committed_sessions):
        assert self._fan_out(storage) == 0
        assert all_jobs(committed_sessions) == []


class TestDeferredRefreshes:
    def test_one_whose_wait_is_over_is_queued_again_and_runs(
        self, me, stub_provider, pool, storage, committed_sessions
    ):
        stub_provider.link(me.user.id, activity_gpx())
        with committed_sessions() as db:
            due = stage_job(
                db,
                me.user.id,
                kind=_Kind.REFRESH,
                status="deferred",
                retry_after=datetime.now(UTC) - timedelta(minutes=1),
            )
            db.commit()

        released = ingestion_service.redispatch_deferred_refreshes(storage)
        pool.drain()

        assert released == 1
        row = read_job(committed_sessions, due.id)
        assert (row.status, row.retry_after) == ("completed", None)
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_a_backlog_larger_than_one_batch_is_queued_a_batch_at_a_time(
        self, me, stub_provider, pool, storage, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(ingestion_service, "_DEFERRED_REDISPATCH_BATCH_SIZE", 2)
        with committed_sessions() as db:
            users = [make_user(db, timezone="UTC") for _ in range(3)]
            for user in users:
                stage_job(
                    db,
                    user.id,
                    kind=_Kind.REFRESH,
                    status="deferred",
                    retry_after=datetime.now(UTC) - timedelta(minutes=1),
                )
            db.commit()

        released = ingestion_service.redispatch_deferred_refreshes(storage)
        pool.drain()

        assert released == 3
        assert {job.status for job in all_jobs(committed_sessions)} == {"completed"}

    def test_one_still_waiting_is_left_alone(self, me, stub_provider, pool, storage, committed_sessions):
        with committed_sessions() as db:
            waiting = stage_job(
                db,
                me.user.id,
                kind=_Kind.REFRESH,
                status="deferred",
                retry_after=datetime.now(UTC) + timedelta(hours=1),
            )
            db.commit()

        assert ingestion_service.redispatch_deferred_refreshes(storage) == 0
        assert read_job(committed_sessions, waiting.id).status == "deferred"
        assert stub_provider.calls == []

    def test_a_duplicate_run_of_a_waiting_job_does_not_claim_it(self, me, stub_provider, committed_sessions, storage):
        with committed_sessions() as db:
            waiting = stage_job(
                db,
                me.user.id,
                kind=_Kind.REFRESH,
                status="deferred",
                retry_after=datetime.now(UTC) + timedelta(hours=1),
            )
            db.commit()

        ingestion_service.run_refresh_job(waiting.id, storage)

        assert read_job(committed_sessions, waiting.id).status == "deferred"
        assert stub_provider.calls == []

    def test_the_stale_job_sweep_does_not_fail_a_job_that_waits_on_purpose(
        self, me, platform, storage, committed_sessions
    ):
        with committed_sessions() as db:
            waiting = stage_job(
                db,
                me.user.id,
                kind=_Kind.REFRESH,
                status="deferred",
                updated_at=datetime.now(UTC) - timedelta(days=3),
                retry_after=datetime.now(UTC) + timedelta(hours=1),
            )
            db.commit()

        ingestion_service.fail_stale_ingestion_jobs(platform.clock, storage)

        assert read_job(committed_sessions, waiting.id).status == "deferred"


class TestRefreshesLostWithThePool:
    @pytest.fixture(autouse=True)
    def _single_process(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 1)

    @pytest.mark.parametrize("status", ["pending", "processing"])
    def test_a_restart_fails_the_refresh_the_lost_pool_held_so_the_next_run_queues_again(
        self, me, status, committed_sessions
    ):
        with committed_sessions() as db:
            lost = stage_job(db, me.user.id, kind=_Kind.REFRESH, status=status)
            db.commit()

        assert ingestion_service.fail_orphaned_local_refreshes() == 1

        row = read_job(committed_sessions, lost.id)
        assert (row.status, row.error_code) == ("failed", _ErrorCode.PROCESSING_FAILED.value)
        with committed_sessions() as db:
            assert ingestion_service.activity_ingestion_crud.get_user_ids_with_active_refresh([me.user.id], db) == set()

    def test_keeps_what_the_pool_does_not_own(self, me, committed_sessions):
        with committed_sessions() as db:
            deferred = stage_job(db, me.user.id, kind=_Kind.REFRESH, status="deferred", retry_after=datetime.now(UTC))
            upload = stage_job(db, me.user.id, staged_key="x.gpx")
            done = stage_job(db, me.user.id, kind=_Kind.REFRESH, status="completed")
            db.commit()

        assert ingestion_service.fail_orphaned_local_refreshes() == 0

        assert [read_job(committed_sessions, job.id).status for job in (deferred, upload, done)] == [
            "deferred",
            "pending",
            "completed",
        ]

    def test_a_durable_worker_keeps_its_leased_refresh(self, me, committed_sessions, monkeypatch):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        with committed_sessions() as db:
            leased = stage_job(db, me.user.id, kind=_Kind.REFRESH, status="processing")
            db.commit()

        assert ingestion_service.fail_orphaned_local_refreshes() == 0
        assert read_job(committed_sessions, leased.id).status == "processing"

    def test_a_sibling_web_workers_refresh_is_left_alone(self, me, committed_sessions, monkeypatch):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 2)
        with committed_sessions() as db:
            sibling = stage_job(db, me.user.id, kind=_Kind.REFRESH, status="processing")
            db.commit()

        assert ingestion_service.fail_orphaned_local_refreshes() == 0
        assert read_job(committed_sessions, sibling.id).status == "processing"


class TestRegisteringAProvider:
    def test_registering_a_name_again_replaces_the_provider_instead_of_asking_it_twice(self, me, providers, pool):
        first = StubProvider().register()
        second = StubProvider().register()
        second.link(me.user.id)

        _refresh(me)
        pool.drain()

        assert (len(first.calls), len(second.calls)) == (0, 1)

    def test_every_registered_provider_is_asked_for_the_same_window(self, me, providers, pool):
        left, right = StubProvider("left").register(), StubProvider("right").register()
        left.link(me.user.id)
        right.link(me.user.id)

        _refresh(me)
        pool.drain()

        assert left.calls[0][1:] == right.calls[0][1:]


class TestARateLimitIsAWarning:
    def test_it_is_logged_as_a_warning_not_an_error(self, me, stub_provider, pool, caplog):
        stub_provider.link(me.user.id)
        stub_provider.failure = _rate_limited(datetime.now(UTC) + timedelta(hours=1))

        with caplog.at_level(logging.WARNING):
            _refresh(me)
            pool.drain()

        assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []
        assert any("rate limited" in record.getMessage() for record in caplog.records)
