"""The durable and bus entry points of a queued profile import or export, run against the real database and
storage."""

import threading
import uuid
from dataclasses import replace

import pytest
from jasil.events import Event, new_event
from jasil.jobs.registry import JobHandlerRegistry
from sqlalchemy import text

import modules.users.users_goals.crud as goals_crud
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.export_service as export_service
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.import_service as import_service
import modules.users.users_profile.import_state_store as import_state_store
import modules.users.users_profile.subscribers as profile_subscribers
import modules.users.users_profile.transfer_pool as transfer_pool
from tests._factories.profile import profile_archive
from tests._factories.users import make_user

_IMPORT_AREA = profile_constants.IMPORT_STAGING_AREA
_GOAL = {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}
_SESSION = uuid.UUID(int=601)


@pytest.fixture(autouse=True)
def _roomy_memory(monkeypatch):
    """The pytest process holds what earlier tests allocated, which the memory limit is not about."""
    imports = import_service.ImportPerformanceConfig(max_memory_mb=1_000_000)
    exports = export_service.ExportPerformanceConfig(max_memory_mb=1_000_000)
    monkeypatch.setattr(import_service.ImportPerformanceConfig, "get_auto_config", classmethod(lambda cls: imports))
    monkeypatch.setattr(export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: exports))


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def imports(platform):
    return import_state_store.ProfileImportStateStore(platform.state)


@pytest.fixture
def exports(platform):
    return export_state_store.ProfileExportStateStore(platform.state)


@pytest.fixture
def blocked_pool():
    release = threading.Event()
    for _ in range(profile_constants.TRANSFER_POOL_MAX_PENDING):
        transfer_pool.pool.submit(release.wait)
    yield
    release.set()
    transfer_pool.pool.shutdown(wait=True)


def _import_event(owner, job_id, key, *, retry_count=0, max_attempts=None) -> Event:
    event = new_event(
        profile_events.USERS_PROFILE_IMPORT_REQUESTED,
        {"user_id": str(owner.id), "job_id": str(job_id), "staged_key": key},
        source="test",
        retry_count=retry_count,
    )
    return replace(event, max_attempts=max_attempts)


def _export_event(owner, job_id, *, retry_count=0, max_attempts=None) -> Event:
    event = new_event(
        profile_events.USERS_PROFILE_EXPORT_REQUESTED,
        {"user_id": str(owner.id), "job_id": str(job_id)},
        source="test",
        retry_count=retry_count,
    )
    return replace(event, max_attempts=max_attempts)


def _staged_import(owner, imports, storage, archive=None):
    job = imports.begin(owner.id, conflict="held")
    key = f"{owner.id}/abc.zip"
    storage.save(_IMPORT_AREA, key, archive or profile_archive(owner, user_goals=[_GOAL]))
    return job, key


def _drain_pool():
    """Wait until the transfer pool has run what it holds: its one worker takes the jobs in order."""
    transfer_pool.pool.submit(lambda: None).result(timeout=60)


def _break_goals(committed_sessions):
    with committed_sessions() as db:
        db.execute(text("DROP TABLE users_goals CASCADE"))
        db.commit()


class TestImport:
    def test_the_durable_handler_runs_the_import_the_event_names(self, committed_sessions, platform, owner, imports):
        job, key = _staged_import(owner, imports, platform.storage)

        profile_subscribers.process_import_requested_for_event(_import_event(owner, job.id, key))

        assert imports.get(owner.id).status == profile_constants.ImportStatus.SUCCEEDED
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 1

    def test_a_durable_attempt_with_attempts_left_asks_to_be_retried(
        self, committed_sessions, platform, owner, imports
    ):
        job, key = _staged_import(owner, imports, platform.storage)
        _break_goals(committed_sessions)

        with pytest.raises(Exception, match="users_goals"):
            profile_subscribers.process_import_requested_for_event(
                _import_event(owner, job.id, key, retry_count=1, max_attempts=3)
            )

        assert imports.get(owner.id).status == profile_constants.ImportStatus.QUEUED

    def test_the_last_durable_attempt_does_not(self, committed_sessions, platform, owner, imports):
        job, key = _staged_import(owner, imports, platform.storage)
        _break_goals(committed_sessions)

        profile_subscribers.process_import_requested_for_event(
            _import_event(owner, job.id, key, retry_count=3, max_attempts=3)
        )

        assert imports.get(owner.id).status == profile_constants.ImportStatus.FAILED

    def test_the_bus_subscriber_never_asks_for_a_retry(self, committed_sessions, platform, owner, imports):
        job, key = _staged_import(owner, imports, platform.storage)
        _break_goals(committed_sessions)

        profile_subscribers.run_import_requested_on_bus(_import_event(owner, job.id, key))
        _drain_pool()

        assert imports.get(owner.id).status == profile_constants.ImportStatus.FAILED

    def test_a_bus_import_waits_its_turn_on_the_transfer_pool_not_on_the_subscriber_thread(
        self, platform, owner, imports
    ):
        job, key = _staged_import(owner, imports, platform.storage)
        release = threading.Event()
        transfer_pool.pool.submit(release.wait)

        profile_subscribers.run_import_requested_on_bus(_import_event(owner, job.id, key))

        # The pool's one worker is busy, so the import is queued behind it and the subscriber has returned.
        assert imports.get(owner.id).status == profile_constants.ImportStatus.QUEUED
        release.set()
        _drain_pool()
        assert imports.get(owner.id).status == profile_constants.ImportStatus.SUCCEEDED

    def test_a_bus_import_the_full_pool_refuses_is_closed_not_left_queued(self, platform, owner, imports, blocked_pool):
        job, key = _staged_import(owner, imports, platform.storage)

        profile_subscribers.run_import_requested_on_bus(_import_event(owner, job.id, key))

        assert imports.get(owner.id).status == profile_constants.ImportStatus.FAILED
        assert platform.storage.list_keys(_IMPORT_AREA, "") == []

    def test_a_dead_lettered_import_is_closed(self, platform, owner, imports):
        job, key = _staged_import(owner, imports, platform.storage)

        profile_subscribers.on_import_requested_dead_letter(_import_event(owner, job.id, key, retry_count=3), "expired")

        assert imports.get(owner.id).status == profile_constants.ImportStatus.FAILED
        assert platform.storage.list_keys(_IMPORT_AREA, "") == []


class TestExport:
    def test_the_durable_handler_runs_the_export_the_event_names(self, platform, owner, exports):
        job = exports.begin(owner.id, _SESSION, conflict="held")

        profile_subscribers.process_export_requested_for_event(_export_event(owner, job.id))

        state = exports.get(owner.id)
        assert state.status == profile_constants.ExportStatus.SUCCEEDED
        assert platform.storage.get(
            profile_constants.EXPORT_STAGING_AREA, profile_constants.export_staged_key(owner.id)
        )

    def test_the_bus_subscriber_hands_the_export_to_the_transfer_pool(self, platform, owner, exports):
        job = exports.begin(owner.id, _SESSION, conflict="held")

        profile_subscribers.run_export_requested_on_bus(_export_event(owner, job.id))
        _drain_pool()

        assert exports.get(owner.id).status == profile_constants.ExportStatus.SUCCEEDED

    def test_a_bus_export_the_full_pool_refuses_is_closed_not_left_queued(self, owner, exports, blocked_pool):
        job = exports.begin(owner.id, _SESSION, conflict="held")

        profile_subscribers.run_export_requested_on_bus(_export_event(owner, job.id))

        assert exports.get(owner.id).status == profile_constants.ExportStatus.FAILED

    def test_a_dead_lettered_export_is_closed(self, owner, exports):
        job = exports.begin(owner.id, _SESSION, conflict="held")

        profile_subscribers.on_export_requested_dead_letter(_export_event(owner, job.id, retry_count=3), None)

        assert exports.get(owner.id).status == profile_constants.ExportStatus.FAILED


class TestRegistration:
    def test_both_transfers_run_when_the_events_are_published_on_the_bus(
        self, committed_sessions, platform, owner, imports, exports
    ):
        profile_subscribers.register_bus_subscribers(platform.events)
        import_job, key = _staged_import(owner, imports, platform.storage)
        export_job = exports.begin(owner.id, _SESSION, conflict="held")

        platform.events.publish(_import_event(owner, import_job.id, key))
        platform.events.publish(_export_event(owner, export_job.id))
        _drain_pool()

        assert imports.get(owner.id).status == profile_constants.ImportStatus.SUCCEEDED
        assert exports.get(owner.id).status == profile_constants.ExportStatus.SUCCEEDED

    def test_both_transfers_are_registered_as_durable_handlers_with_their_dead_letter_callbacks(self):
        registry = JobHandlerRegistry()

        profile_subscribers.register_durable_handlers(registry)

        assert registry.subscribers_for(profile_events.USERS_PROFILE_IMPORT_REQUESTED) == (
            profile_subscribers.IMPORT_REQUESTED_SUBSCRIBER_ID,
        )
        assert registry.subscribers_for(profile_events.USERS_PROFILE_EXPORT_REQUESTED) == (
            profile_subscribers.EXPORT_REQUESTED_SUBSCRIBER_ID,
        )
        assert registry.dead_letter_subscriber_ids() == {
            profile_subscribers.IMPORT_REQUESTED_SUBSCRIBER_ID,
            profile_subscribers.EXPORT_REQUESTED_SUBSCRIBER_ID,
        }
