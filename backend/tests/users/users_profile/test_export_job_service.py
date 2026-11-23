"""Profile export jobs on the real database and storage: accepting, running, serving and sweeping exports."""

import os
import threading
import time
import uuid

import pytest
from jasil.audit.models import AuditLog
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import select, text

import core.attempt_state as core_attempt_state
import core.config as core_config
import core.exceptions as core_exceptions
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.schema as auth_schema
import modules.users.users.constants as users_constants
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.export_job_service as job_service
import modules.users.users_profile.export_service as export_service
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.transfer_pool as transfer_pool
from tests._factories.profile import FaultyStorage
from tests._factories.users import PASSWORD, make_user

_Status = profile_constants.ExportStatus
_Failure = profile_constants.ExportFailure
_AREA = profile_constants.EXPORT_STAGING_AREA
_SESSION = uuid.UUID(int=601)
_ROOMY = {"max_memory_mb": 1_000_000}


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def storage(platform):
    return platform.storage


@pytest.fixture
def states(platform):
    return export_state_store.ProfileExportStateStore(platform.state)


@pytest.fixture
def step_up_store(platform):
    return account_security_integration.get_step_up_attempts(platform.state)


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def requested(platform):
    """The export-requested events the bus carries."""
    seen = []
    platform.events.subscribe(profile_events.USERS_PROFILE_EXPORT_REQUESTED, seen.append)
    return seen


@pytest.fixture(autouse=True)
def _small_memory_footprint(monkeypatch):
    """The pytest process holds what earlier tests allocated, which the memory limit is not about."""
    config = export_service.ExportPerformanceConfig(**_ROOMY)
    monkeypatch.setattr(export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: config))


def _request(committed_sessions, owner, states, step_up_store, password=PASSWORD):
    with committed_sessions() as db:
        return job_service.request_export(
            owner.id, _SESSION, auth_schema.StepUpVerification(current_password=password), step_up_store, states, db
        )


def _payload(owner_id, job_id):
    return profile_events.ProfileExportRequestedPayload(user_id=owner_id, job_id=job_id)


def _run(owner_id, job_id, states, storage, *, will_retry=False):
    job_service.run_export(_payload(owner_id, job_id), states, storage, will_retry=will_retry)


def _audit(committed_sessions, action):
    with committed_sessions() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action_id == action)).all()


def _supersede(states, state, owner_id):
    """Return a first export whose claim expired, and a second one that began after it."""
    first = states.begin(owner_id, _SESSION, conflict="held")
    state.delete(core_attempt_state.key("users", "profile_export:claim", str(owner_id)))
    return first, states.begin(owner_id, _SESSION, conflict="held")


@pytest.fixture
def blocked_pool():
    """Fill the local transfer pool with jobs that wait, and release them afterwards."""
    release = threading.Event()
    for _ in range(profile_constants.TRANSFER_POOL_MAX_PENDING):
        transfer_pool.pool.submit(release.wait)
    yield
    release.set()
    transfer_pool.pool.shutdown(wait=True)


class TestRequestExport:
    def test_the_export_is_queued_audited_and_published_for_a_worker(
        self, committed_sessions, owner, states, step_up_store, requested
    ):
        status = _request(committed_sessions, owner, states, step_up_store)

        assert status.status == "queued"
        assert [event.payload["job_id"] for event in requested] == [str(status.id)]
        assert states.get(owner.id, job_id=status.id).status == _Status.QUEUED
        assert states.get(owner.id).session_id == _SESSION
        rows = _audit(committed_sessions, profile_audit_actions.PROFILE_EXPORT_REQUEST.id)
        assert [row.target_owner_id for row in rows] == [str(owner.id)]

    def test_a_wrong_password_claims_nothing_and_publishes_nothing(
        self, committed_sessions, owner, states, step_up_store, requested
    ):
        with pytest.raises(core_exceptions.StepUpFailedError):
            _request(committed_sessions, owner, states, step_up_store, password="wrong")

        assert states.get(owner.id) is None
        assert requested == []

    def test_a_pending_export_refuses_a_second(self, committed_sessions, owner, states, step_up_store):
        _request(committed_sessions, owner, states, step_up_store)

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            _request(committed_sessions, owner, states, step_up_store)

    def test_a_full_local_pool_refuses_before_the_claim_is_taken(
        self, committed_sessions, owner, states, step_up_store, blocked_pool
    ):
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            _request(committed_sessions, owner, states, step_up_store)

        assert states.get(owner.id) is None

    def test_a_durable_deployment_does_not_look_at_the_local_pool(
        self, committed_sessions, owner, states, step_up_store, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)

        status = _request(committed_sessions, owner, states, step_up_store)

        assert status.status == "queued"

    def test_a_failure_to_queue_closes_the_state_and_frees_the_claim(
        self, committed_sessions, owner, states, step_up_store
    ):
        with committed_sessions() as db:
            db.execute(text("DROP TABLE jasil_audit_log CASCADE"))
            db.commit()

        with pytest.raises(Exception, match="jasil_audit_log"):
            _request(committed_sessions, owner, states, step_up_store)

        assert states.get(owner.id).status == _Status.FAILED
        states.begin(owner.id, _SESSION, conflict="held")

    def test_an_export_the_pool_could_not_take_is_closed(self, owner, states):
        job = states.begin(owner.id, _SESSION, conflict="held")

        job_service.fail_unstarted_export(_payload(owner.id, job.id), states)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)


class TestRunExport:
    def test_a_finished_export_is_staged_and_records_its_size(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")

        _run(owner.id, job.id, states, storage)

        state = states.get(owner.id)
        staged = storage.get(_AREA, profile_constants.export_staged_key(owner.id))
        assert staged is not None
        assert (state.status, state.size_bytes) == (_Status.SUCCEEDED, len(staged))
        assert state.expires_at is not None
        states.begin(owner.id, _SESSION, conflict="held")

    @pytest.mark.parametrize("finished", [_Status.SUCCEEDED, _Status.FAILED])
    def test_a_redelivery_of_a_finished_export_does_nothing(self, owner, states, storage, finished):
        job = states.begin(owner.id, _SESSION, conflict="held")
        states.set_status(owner.id, job.id, finished)

        _run(owner.id, job.id, states, storage)

        assert storage.get(_AREA, profile_constants.export_staged_key(owner.id)) is None
        assert states.get(owner.id).status == finished

    def test_a_superseded_export_leaves_the_newer_exports_state_and_claim(self, platform, owner, storage):
        states = export_state_store.ProfileExportStateStore(platform.state)
        first, second = _supersede(states, platform.state, owner.id)

        _run(owner.id, first.id, states, storage)

        assert storage.get(_AREA, profile_constants.export_staged_key(owner.id)) is None
        assert states.get(owner.id, job_id=second.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(owner.id, _SESSION, conflict="held")

    def test_a_redelivery_after_a_worker_died_builds_again(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        states.set_status(owner.id, job.id, _Status.RUNNING)

        _run(owner.id, job.id, states, storage)

        assert states.get(owner.id).status == _Status.SUCCEEDED

    def test_a_storage_failure_is_retried_while_attempts_remain(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        unreachable = FaultyStorage(storage, faults={"save_stream": OSError("storage down")})

        with pytest.raises(OSError, match="storage down"):
            _run(owner.id, job.id, states, unreachable, will_retry=True)

        assert states.get(owner.id).status == _Status.QUEUED

    def test_a_storage_outage_while_reading_the_photo_is_retried_while_attempts_remain(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        storage.save(users_constants.USER_IMAGE_STORAGE_AREA, f"{owner.id}.png", b"png")
        down = FaultyStorage(
            storage,
            key_faults={("get", f"{owner.id}.png"): StorageBackendUnavailableError("storage down")},
        )

        with pytest.raises(StorageBackendUnavailableError, match="storage down"):
            _run(owner.id, job.id, states, down, will_retry=True)

        assert states.get(owner.id).status == _Status.QUEUED

    def test_a_storage_refusal_while_reading_the_photo_skips_it_and_the_export_completes(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        storage.save(users_constants.USER_IMAGE_STORAGE_AREA, f"{owner.id}.png", b"png")
        refused = FaultyStorage(
            storage,
            key_faults={("get", f"{owner.id}.png"): StorageBackendUnavailableError("access denied", transient=False)},
        )

        _run(owner.id, job.id, states, refused, will_retry=True)

        assert states.get(owner.id).status == _Status.SUCCEEDED

    def test_a_database_failure_wrapped_by_the_collection_is_retried(self, committed_sessions, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        with committed_sessions() as db:
            db.execute(text("DROP TABLE health_weight CASCADE"))
            db.commit()

        with pytest.raises(core_exceptions.DomainError):
            _run(owner.id, job.id, states, storage, will_retry=True)

        assert states.get(owner.id).status == _Status.QUEUED

    def test_a_transient_failure_on_the_last_attempt_is_final(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        unreachable = FaultyStorage(storage, faults={"save_stream": OSError("storage down")})

        _run(owner.id, job.id, states, unreachable, will_retry=False)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)

    def test_a_timeout_is_reported_as_one_and_never_retried(self, owner, states, storage, monkeypatch):
        config = export_service.ExportPerformanceConfig(timeout_seconds=-1, **_ROOMY)
        monkeypatch.setattr(export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: config))
        job = states.begin(owner.id, _SESSION, conflict="held")

        _run(owner.id, job.id, states, storage, will_retry=True)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.TIMED_OUT)

    def test_a_failure_of_another_kind_is_final_with_a_sanitized_code(self, states, storage):
        stranger = uuid.uuid4()
        job = states.begin(stranger, _SESSION, conflict="held")

        _run(stranger, job.id, states, storage, will_retry=True)

        state = states.get(stranger)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        assert str(stranger) not in state.model_dump_json()


class TestOpenExport:
    @pytest.fixture
    def finished(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        _run(owner.id, job.id, states, storage)

    def test_the_staged_archive_is_streamed_to_the_session_that_asked_and_audited(
        self, committed_sessions, owner, states, storage, finished
    ):
        chunks, size = job_service.open_export(owner.id, _SESSION, states, storage)

        data = b"".join(chunks)

        assert data == storage.get(_AREA, profile_constants.export_staged_key(owner.id))
        assert size == len(data)
        rows = _audit(committed_sessions, profile_audit_actions.PROFILE_EXPORT_DOWNLOAD.id)
        assert [row.target_owner_id for row in rows] == [str(owner.id)]

    def test_another_session_of_the_user_gets_no_download(self, owner, states, storage, finished):
        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(owner.id, uuid.uuid4(), states, storage)

    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING, _Status.FAILED])
    def test_an_export_that_is_not_finished_has_no_download(self, owner, states, storage, status):
        job = states.begin(owner.id, _SESSION, conflict="held")
        states.set_status(owner.id, job.id, status)

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(owner.id, _SESSION, states, storage)

    def test_an_export_nobody_requested_has_no_download(self, owner, states, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(owner.id, _SESSION, states, storage)

    def test_a_missing_archive_is_not_found(self, owner, states, storage, finished):
        storage.delete(_AREA, profile_constants.export_staged_key(owner.id))

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(owner.id, _SESSION, states, storage)


class TestSweepStagedExports:
    def _stage(self, storage, name, *, age_seconds):
        storage.save(_AREA, name, b"zip")
        path = storage._resolve(_AREA, name)
        aged = time.time() - age_seconds
        os.utime(path, (aged, aged))

    def test_removes_only_archives_past_the_age(self, storage):
        self._stage(storage, f"{uuid.uuid4()}.zip", age_seconds=7200)
        fresh = f"{uuid.uuid4()}.zip"
        self._stage(storage, fresh, age_seconds=0)

        removed = job_service.sweep_staged_exports(storage, 3600)

        assert removed == 1
        assert storage.list_keys(_AREA, "") == [fresh]

    def test_nothing_stale_removes_nothing(self, storage):
        self._stage(storage, f"{uuid.uuid4()}.zip", age_seconds=0)

        assert job_service.sweep_staged_exports(storage, 3600) == 0

    def test_one_failing_delete_does_not_stop_the_rest(self, storage):
        stuck, other = f"{uuid.uuid4()}.zip", f"{uuid.uuid4()}.zip"
        self._stage(storage, stuck, age_seconds=7200)
        self._stage(storage, other, age_seconds=7200)
        busy = FaultyStorage(storage, key_faults={("delete", stuck): StorageBackendUnavailableError("busy")})

        removed = job_service.sweep_staged_exports(busy, 3600)

        assert removed == 1
        assert storage.list_keys(_AREA, "") == [stuck]


class TestDiscardStagedExport:
    def test_removes_the_users_archive_and_only_theirs(self, owner, storage):
        mine = profile_constants.export_staged_key(owner.id)
        theirs = profile_constants.export_staged_key(uuid.uuid4())
        storage.save(_AREA, mine, b"zip")
        storage.save(_AREA, theirs, b"zip")

        job_service.discard_staged_export(owner.id, storage)

        assert storage.list_keys(_AREA, "") == [theirs]

    def test_a_storage_failure_is_logged_not_raised(self, owner, storage):
        storage.save(_AREA, profile_constants.export_staged_key(owner.id), b"zip")
        down = FaultyStorage(storage, faults={"delete": StorageBackendUnavailableError("down")})

        job_service.discard_staged_export(owner.id, down)

        assert storage.list_keys(_AREA, "") == [profile_constants.export_staged_key(owner.id)]

    def test_an_unexpected_error_propagates(self, owner, storage):
        broken = FaultyStorage(storage, faults={"delete": RuntimeError("bug")})

        with pytest.raises(RuntimeError, match="bug"):
            job_service.discard_staged_export(owner.id, broken)


class TestCloseDeadLetteredExport:
    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING])
    def test_a_pending_export_is_failed_and_its_claim_released(self, owner, states, status):
        job = states.begin(owner.id, _SESSION, conflict="held")
        states.set_status(owner.id, job.id, status)

        job_service.close_dead_lettered_export(_payload(owner.id, job.id), states)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        states.begin(owner.id, _SESSION, conflict="held")

    def test_a_superseded_export_leaves_the_newer_exports_state_and_claim(self, platform, owner):
        states = export_state_store.ProfileExportStateStore(platform.state)
        first, second = _supersede(states, platform.state, owner.id)

        job_service.close_dead_lettered_export(_payload(owner.id, first.id), states)

        assert states.get(owner.id, job_id=second.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(owner.id, _SESSION, conflict="held")

    def test_an_export_that_already_finished_keeps_its_outcome(self, owner, states, storage):
        job = states.begin(owner.id, _SESSION, conflict="held")
        _run(owner.id, job.id, states, storage)

        job_service.close_dead_lettered_export(_payload(owner.id, job.id), states)

        assert states.get(owner.id).status == _Status.SUCCEEDED

    def test_an_expired_state_is_not_resurrected(self, owner, states):
        job_service.close_dead_lettered_export(_payload(owner.id, uuid.uuid4()), states)

        assert states.get(owner.id) is None
