"""On the durable profile a request stages its job in the outbox and a worker's handler runs it.

The route and the handlers are the production ones; the outbox row a request leaves is turned back into the event a
worker receives, and handed to the handler the registry holds. Nothing runs on the in-process pool.
"""

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jasil.jobs.registry as jobs_registry
import pytest
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from pydantic import ValidationError

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.service as ingestion_service
import modules.activities.activity_ingestion.subscribers as ingestion_subscribers
from tests._factories.garmin import EMPTY_GPX, activity_gpx
from tests._factories.ingestion import (
    activities_of,
    all_jobs,
    queued_events,
    read_job,
    stage_job,
    staged_keys,
)
from tests._factories.profile import FaultyStorage
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
_Kind = ingestion_constants.IngestionJobKind
_ErrorCode = ingestion_constants.IngestionJobErrorCode


@pytest.fixture(autouse=True)
def _durable(durable_jobs):
    """Every test here runs on the durable profile."""


@pytest.fixture
def registry() -> JobHandlerRegistry:
    """The registry the ingestion handlers are registered in, as a worker holds them."""
    return jobs_registry.registry


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _upload(user, content: bytes = b"", name: str = "ride.gpx"):
    return user.client.post(f"{_API}/activities/upload", files={"file": (name, content or activity_gpx())})


def _event_for(event_type: str, job_id: uuid.UUID, *, retry_count: int = 1) -> Event:
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        source="test",
        timestamp="2026-01-01T00:00:00+00:00",
        payload={"job_id": str(job_id)},
        retry_count=retry_count,
        max_attempts=3,
    )


class TestAnAcceptedUpload:
    def test_is_staged_in_the_outbox_for_a_worker_and_not_run_in_process(self, me, pool, committed_sessions, storage):
        response = _upload(me)

        assert response.status_code == 202
        (event,) = queued_events(committed_sessions)
        assert event.event_type == ingestion_events.ACTIVITY_FILE_UPLOADED
        assert event.payload["job_id"] == response.json()["id"]
        assert set(event.payload) <= {"job_id", "schema_version"}, "the owner and the key are columns, not payload"
        assert pool.futures == []
        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert row.status == "pending"
        assert len(staged_keys(storage)) == 1

    def test_is_imported_by_the_handler_the_worker_runs(self, me, registry, committed_sessions, storage, hints):
        response = _upload(me, activity_gpx(name="Evening Ride"))
        (event,) = queued_events(committed_sessions)

        registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(event)

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        (activity,) = activities_of(committed_sessions, me.user.id)
        assert (row.status, row.activity_ids) == ("completed", [str(activity.id)])
        assert file_storage.get_activity_file(activity.id, storage) is not None
        assert staged_keys(storage) == []
        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]

    def test_run_again_after_it_succeeded_does_not_import_it_twice(self, me, registry, committed_sessions):
        _upload(me)
        (event,) = queued_events(committed_sessions)
        handler = registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)

        handler(event)
        handler(event)

        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_a_file_that_is_not_an_activity_fails_at_once_without_spending_a_retry(
        self, me, registry, committed_sessions, storage
    ):
        response = _upload(me, EMPTY_GPX)
        (event,) = queued_events(committed_sessions)

        registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(event)

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", _ErrorCode.INVALID_FILE.value)
        assert staged_keys(storage) == []

    def test_a_storage_outage_is_left_for_the_retry_with_the_blob_kept(self, me, committed_sessions, storage, platform):
        response = _upload(me)
        job_id = uuid.UUID(response.json()["id"])
        down = FaultyStorage(storage, faults={"open_stream": OSError("storage is down")})

        with pytest.raises(core_exceptions.ProcessingError):
            ingestion_service.run_upload_job(job_id, down)

        assert read_job(committed_sessions, job_id).status == "pending"
        assert len(staged_keys(storage)) == 1
        ingestion_service.run_upload_job(job_id, storage)
        assert read_job(committed_sessions, job_id).status == "completed"
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_a_malformed_event_is_refused(self, registry):
        event = _event_for(ingestion_events.ACTIVITY_FILE_UPLOADED, uuid.uuid4())
        event.payload["job_id"] = "not-a-uuid"

        with pytest.raises(ValidationError):
            registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(event)


class TestAnEventForAJobThatIsGone:
    def test_an_upload_that_was_pruned_is_ignored(self, registry, committed_sessions):
        event = _event_for(ingestion_events.ACTIVITY_FILE_UPLOADED, uuid.uuid4())

        registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(event)

        assert all_jobs(committed_sessions) == []

    def test_a_refresh_that_was_pruned_is_ignored(self, registry, stub_provider):
        event = _event_for(ingestion_events.ACTIVITY_REFRESH_REQUESTED, uuid.uuid4())

        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)

        assert stub_provider.calls == []

    def test_a_completed_refresh_is_not_run_again_or_reopened(self, me, registry, stub_provider, committed_sessions):
        stub_provider.link(me.user.id)
        with committed_sessions() as db:
            done = stage_job(db, me.user.id, kind=_Kind.REFRESH, status="completed")
            db.commit()

        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(
            _event_for(ingestion_events.ACTIVITY_REFRESH_REQUESTED, done.id)
        )

        assert stub_provider.calls == []
        assert read_job(committed_sessions, done.id).status == "completed"


class TestAnAcceptedRefresh:
    def test_is_staged_in_the_outbox_and_runs_when_the_worker_handles_it(
        self, me, registry, stub_provider, pool, committed_sessions
    ):
        stub_provider.link(me.user.id, activity_gpx())

        response = me.client.post(f"{_API}/activities/refresh")

        assert response.status_code == 202
        (event,) = queued_events(committed_sessions)
        assert event.event_type == ingestion_events.ACTIVITY_REFRESH_REQUESTED
        assert pool.futures == []
        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)
        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, len(row.activity_ids)) == ("completed", 1)

    @pytest.mark.parametrize("retry_at", [datetime.now(UTC) + timedelta(hours=2), None], ids=["limit-known", "unknown"])
    def test_a_rate_limited_provider_defers_the_job_without_raising_so_no_retry_is_spent(
        self, me, registry, stub_provider, committed_sessions, retry_at
    ):
        stub_provider.link(me.user.id)
        stub_provider.failure = core_exceptions.TooManyRequestsError(
            "Provider rate limit", scope=core_exceptions.TooManyRequestsScope.PROVIDER, retry_at=retry_at
        )
        response = me.client.post(f"{_API}/activities/refresh")
        (event,) = queued_events(committed_sessions)

        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("deferred", None)
        assert row.retry_after > datetime.now(UTC)

    def test_a_deferral_is_one_info_line_as_the_provider_already_reported_its_limit(
        self, me, registry, stub_provider, committed_sessions, app_log
    ):
        stub_provider.link(me.user.id)
        stub_provider.failure = core_exceptions.TooManyRequestsError(
            "Provider rate limit", scope=core_exceptions.TooManyRequestsScope.PROVIDER, retry_at=None
        )
        response = me.client.post(f"{_API}/activities/refresh")
        (event,) = queued_events(committed_sessions)

        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)

        lines = [
            record
            for record in app_log.records
            if record.levelno > logging.DEBUG and "rate limit" in record.getMessage().lower()
        ]
        assert [(record.levelno, record.getMessage(), record.job_id) for record in lines] == [
            (logging.INFO, "Provider refresh deferred until the rate limit clears", uuid.UUID(response.json()["id"]))
        ]

    def test_a_provider_failure_is_raised_for_the_retry_and_the_job_stays_claimable(
        self, me, registry, stub_provider, committed_sessions
    ):
        stub_provider.link(me.user.id)
        stub_provider.failure = RuntimeError("provider is down")
        response = me.client.post(f"{_API}/activities/refresh")
        (event,) = queued_events(committed_sessions)

        with pytest.raises(core_exceptions.ProcessingError):
            registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)

        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).status == "pending"
        stub_provider.failure = None
        registry.get(ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID)(event)
        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).status == "completed"


class TestScheduledWork:
    def test_the_fan_out_stages_one_event_per_user_and_runs_nothing_inline(
        self, stub_provider, pool, storage, committed_sessions
    ):
        with committed_sessions() as db:
            users = [make_user(db, timezone="UTC") for _ in range(2)]
            db.commit()
        for user in users:
            stub_provider.link(user.id)

        queued = ingestion_service.enqueue_scheduled_refreshes(storage)

        assert queued == 2
        events = queued_events(committed_sessions)
        assert {event.payload["job_id"] for event in events} == {str(job.id) for job in all_jobs(committed_sessions)}
        assert pool.futures == []
        assert stub_provider.calls == []

    def test_a_deferred_refresh_whose_wait_is_over_is_published_to_a_worker(
        self, me, pool, storage, committed_sessions
    ):
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

        assert released == 1
        assert [event.payload["job_id"] for event in queued_events(committed_sessions)] == [str(due.id)]
        assert read_job(committed_sessions, due.id).status == "pending"
        assert pool.futures == []

    def test_uploads_and_bulk_imports_are_left_to_the_workers_lease_after_a_restart(
        self, me, pool, storage, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 1)
        with committed_sessions() as db:
            leased = stage_job(db, me.user.id, status="processing", staged_key="x.gpx")
            db.commit()

        assert ingestion_service.resume_orphaned_local_jobs(storage, lambda *_a: None) == 0
        assert read_job(committed_sessions, leased.id).status == "processing"


class TestADeadLetteredJob:
    @pytest.mark.parametrize(
        ("kind", "event_type", "subscriber_id", "code"),
        [
            pytest.param(
                _Kind.UPLOAD,
                ingestion_events.ACTIVITY_FILE_UPLOADED,
                ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
                _ErrorCode.PROCESSING_FAILED,
                id="upload",
            ),
            pytest.param(
                _Kind.REFRESH,
                ingestion_events.ACTIVITY_REFRESH_REQUESTED,
                ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID,
                _ErrorCode.PROVIDER_UNAVAILABLE,
                id="refresh",
            ),
            pytest.param(
                _Kind.BULK_IMPORT,
                ingestion_events.ACTIVITY_BULK_IMPORT_CONTINUE,
                ingestion_subscribers.BULK_IMPORT_SUBSCRIBER_ID,
                _ErrorCode.PROCESSING_FAILED,
                id="bulk-import",
            ),
        ],
    )
    def test_is_closed_with_that_jobs_reason_and_its_owner_is_told(
        self, me, registry, committed_sessions, hints, kind, event_type, subscriber_id, code
    ):
        options = {"import_source": "generic", "files_total": 1} if kind is _Kind.BULK_IMPORT else {}
        with committed_sessions() as db:
            job = stage_job(db, me.user.id, kind=kind, status="processing", **options)
            db.commit()

        registry.dead_letter_callback(subscriber_id)(_event_for(event_type, job.id), "gave up")

        row = read_job(committed_sessions, job.id)
        assert (row.status, row.error_code) == ("failed", code.value)
        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]

    def test_an_upload_gives_up_its_staged_blob(self, me, registry, committed_sessions, storage):
        response = _upload(me)
        (event,) = queued_events(committed_sessions)

        registry.dead_letter_callback(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(event, "gave up")

        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).status == "failed"
        assert staged_keys(storage) == []

    def test_closing_a_job_that_is_already_terminal_changes_nothing_and_tells_nobody(
        self, me, registry, committed_sessions, hints
    ):
        with committed_sessions() as db:
            done = stage_job(db, me.user.id, status="completed", activity_ids=[uuid.uuid4()])
            db.commit()

        registry.dead_letter_callback(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID)(
            _event_for(ingestion_events.ACTIVITY_FILE_UPLOADED, done.id), "gave up"
        )

        assert read_job(committed_sessions, done.id).status == "completed"
        assert hints == []

    def test_every_handler_is_registered_with_its_callback(self, registry):
        assert registry.dead_letter_subscriber_ids() >= {
            ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
            ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID,
            ingestion_subscribers.BULK_IMPORT_SUBSCRIBER_ID,
        }
        assert registry.subscribers_for(ingestion_events.ACTIVITY_FILE_UPLOADED) == (
            ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
        )


class TestTheLocalPoolOnTheDurableProfile:
    """Only work that needs this process's own disk runs on the pool whatever the profile."""

    @pytest.fixture
    def full_pool(self, monkeypatch):
        release = threading.Event()
        full = core_local_pool.BoundedPool("full", workers=1, max_pending=1)
        monkeypatch.setattr(ingestion_background, "_pool", full)
        full.submit(release.wait, 10)
        yield full
        release.set()
        full.shutdown(wait=True)

    def test_a_full_pool_does_not_refuse_an_upload_a_worker_will_run(self, me, full_pool, committed_sessions):
        response = _upload(me)

        assert response.status_code == 202
        assert len(queued_events(committed_sessions)) == 1

    def test_a_full_pool_does_refuse_a_folder_import_only_this_node_can_pack(self, me, full_pool, committed_sessions):
        Path(core_config.bulk_import_dir_for(me.user.id)).mkdir(parents=True)
        (Path(core_config.bulk_import_dir_for(me.user.id)) / "a.gpx").write_bytes(activity_gpx())

        response = me.client.post(f"{_API}/activities/bulk-import/folder")

        assert response.status_code == 503
        assert all_jobs(committed_sessions) == []
