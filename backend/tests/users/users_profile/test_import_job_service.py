"""Profile import jobs on the real database and storage: accepting, running, failing and sweeping imports."""

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
import modules.users.users.integration_service as users_integration
import modules.users.users_goals.crud as goals_crud
import modules.users.users_profile.audit_actions as profile_audit_actions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.import_job_service as job_service
import modules.users.users_profile.import_service as import_service
import modules.users.users_profile.import_state_store as import_state_store
import modules.users.users_profile.transfer_pool as transfer_pool
from tests._factories.profile import FaultyStorage, archive_of, png, profile_archive
from tests._factories.users import make_user

_Status = profile_constants.ImportStatus
_Failure = profile_constants.ImportFailure
_AREA = profile_constants.IMPORT_STAGING_AREA
_ROOMY = {"max_memory_mb": 1_000_000}
_GOAL = {"interval": "daily", "activity_type": "run", "goal_type": "activities", "goal_activities_number": 1}


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def storage(platform):
    return platform.storage


@pytest.fixture
def states(platform):
    return import_state_store.ProfileImportStateStore(platform.state)


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, city="Porto")
        db.commit()
    return created


@pytest.fixture
def requested(platform):
    """The import-requested events the bus carries."""
    seen = []
    platform.events.subscribe(profile_events.USERS_PROFILE_IMPORT_REQUESTED, seen.append)
    return seen


def _use_config(monkeypatch, **settings):
    config = import_service.ImportPerformanceConfig(**{**_ROOMY, **settings})
    monkeypatch.setattr(import_service.ImportPerformanceConfig, "get_auto_config", classmethod(lambda cls: config))


@pytest.fixture(autouse=True)
def _default_config(monkeypatch):
    """The pytest process holds what earlier tests allocated, which the memory limit is not about."""
    _use_config(monkeypatch)


def _saver(data: bytes):
    """An upload saver that writes ``data`` where the shared validator would."""

    def save(*, kind, upload_dir, filename):
        path = os.path.join(upload_dir, filename)
        with open(path, "wb") as out:
            out.write(data)
        return path

    return save


def _rejecting(*, kind, upload_dir, filename):
    raise core_exceptions.InvalidInputError("not a zip")


def _stage(storage, owner_id, archive, name="abc.zip"):
    key = f"{owner_id}/{name}"
    storage.save(_AREA, key, archive)
    return key


def _payload(owner_id, job_id, key):
    return profile_events.ProfileImportRequestedPayload(user_id=owner_id, job_id=job_id, staged_key=key)


def _queued(states, owner_id):
    return states.begin(owner_id, conflict="held")


def _run(owner_id, job, states, storage, key, *, will_retry=False):
    job_service.run_import(_payload(owner_id, job.id, key), states, storage, will_retry=will_retry)


def _audit(committed_sessions, action):
    with committed_sessions() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action_id == action)).all()


def _supersede(states, state, owner_id):
    first = states.begin(owner_id, conflict="held")
    state.delete(core_attempt_state.key("users", "profile_import:claim", str(owner_id)))
    return first, states.begin(owner_id, conflict="held")


@pytest.fixture
def blocked_pool():
    release = threading.Event()
    for _ in range(profile_constants.TRANSFER_POOL_MAX_PENDING):
        transfer_pool.pool.submit(release.wait)
    yield
    release.set()
    transfer_pool.pool.shutdown(wait=True)


class TestRequestImport:
    def test_the_archive_is_staged_under_the_users_prefix_audited_and_published(
        self, committed_sessions, owner, states, storage, requested
    ):
        with committed_sessions() as db:
            status = job_service.request_import(owner.id, _saver(b"archive-bytes"), states, storage, db)

        assert status.status == "queued"
        (event,) = requested
        key = event.payload["staged_key"]
        assert key.startswith(f"{owner.id}/") and key.endswith(".zip")
        assert event.payload["job_id"] == str(status.id)
        assert storage.get(_AREA, key) == b"archive-bytes"
        assert states.get(owner.id, job_id=status.id).status == _Status.QUEUED
        rows = _audit(committed_sessions, profile_audit_actions.PROFILE_IMPORT_REQUEST.id)
        assert [row.target_owner_id for row in rows] == [str(owner.id)]

    def test_a_pending_import_refuses_a_second_and_stages_nothing(self, committed_sessions, owner, states, storage):
        _queued(states, owner.id)
        read = []

        def saver(**kwargs):
            read.append(kwargs)

        with committed_sessions() as db, pytest.raises(core_exceptions.JobAlreadyRunningError):
            job_service.request_import(owner.id, saver, states, storage, db)

        assert read == []
        assert storage.list_keys(_AREA, "") == []

    def test_a_rejected_archive_frees_the_claim_and_records_no_import(
        self, committed_sessions, owner, states, storage, requested
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError):
            job_service.request_import(owner.id, _rejecting, states, storage, db)

        assert states.get(owner.id) is None
        assert storage.list_keys(_AREA, "") == []
        assert requested == []
        states.begin(owner.id, conflict="held")

    def test_a_full_local_pool_refuses_before_anything_is_staged(
        self, committed_sessions, owner, states, storage, blocked_pool
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.ServiceUnavailableError):
            job_service.request_import(owner.id, _saver(b"zip"), states, storage, db)

        assert states.get(owner.id) is None
        assert storage.list_keys(_AREA, "") == []

    def test_a_durable_deployment_does_not_look_at_the_local_pool(
        self, committed_sessions, owner, states, storage, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)

        with committed_sessions() as db:
            status = job_service.request_import(owner.id, _saver(b"zip"), states, storage, db)

        assert status.status == "queued"

    def test_a_failure_to_queue_removes_the_archive_and_closes_the_state(
        self, committed_sessions, owner, states, storage
    ):
        with committed_sessions() as db:
            db.execute(text("DROP TABLE jasil_audit_log CASCADE"))
            db.commit()

        with committed_sessions() as db, pytest.raises(Exception, match="jasil_audit_log"):
            job_service.request_import(owner.id, _saver(b"zip"), states, storage, db)

        assert storage.list_keys(_AREA, "") == []
        assert states.get(owner.id).status == _Status.FAILED
        states.begin(owner.id, conflict="held")

    def test_an_import_the_pool_could_not_take_is_closed_and_its_archive_removed(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, b"zip")

        job_service.fail_unstarted_import(_payload(owner.id, job.id, key), states, storage)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        assert storage.list_keys(_AREA, "") == []
        rows = _audit(committed_sessions, profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)
        assert [row.outcome for row in rows] == ["failure"]


class TestRunImport:
    def test_a_successful_import_records_the_counts_and_removes_the_archive(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))

        _run(owner.id, job, states, storage, key)

        state = states.get(owner.id)
        assert state.status == _Status.SUCCEEDED
        assert state.imported["user_goals"] == 1
        assert storage.list_keys(_AREA, "") == []
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 1
        rows = _audit(committed_sessions, profile_audit_actions.PROFILE_IMPORT_COMPLETE.id)
        assert [row.outcome for row in rows] == ["success"]
        states.begin(owner.id, conflict="held")

    @pytest.mark.parametrize(
        ("build", "failure"),
        [
            (lambda owner, stranger: b"not an archive", _Failure.INVALID_FILE),
            (lambda owner, stranger: archive_of({"data/user.json": b"{ not json"}), _Failure.INVALID_FILE),
            (
                lambda owner, stranger: archive_of({"data/user.json": [{"weight_units": "stones"}]}),
                _Failure.INVALID_FILE,
            ),
            (lambda owner, stranger: profile_archive(stranger, user_goals=[_GOAL]), _Failure.WRONG_ACCOUNT),
            (lambda owner, stranger: archive_of({"data/user.json": [{"id": 3}]}), _Failure.OLDER_VERSION),
            (lambda owner, stranger: archive_of({"data/readme.json": []}), _Failure.INVALID_FILE),
        ],
        ids=["not-a-zip", "bad-json", "bad-profile", "wrong-account", "older-version", "nothing-to-import"],
    )
    def test_a_rejected_archive_is_final_with_the_code_that_names_the_fault(
        self, committed_sessions, owner, states, storage, build, failure
    ):
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, build(owner, stranger))

        _run(owner.id, job, states, storage, key, will_retry=True)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, failure)
        assert storage.list_keys(_AREA, "") == []
        states.begin(owner.id, conflict="held")

    @pytest.mark.parametrize(
        ("settings", "archive", "failure"),
        [
            ({"max_file_size_mb": 0}, lambda owner: profile_archive(owner, user_goals=[_GOAL]), _Failure.TOO_LARGE),
            (
                {"max_activities": 0},
                lambda owner: profile_archive(owner, activities=[{"id": str(uuid.uuid4())}]),
                _Failure.TOO_MANY_ACTIVITIES,
            ),
            ({"timeout_seconds": -1}, lambda owner: profile_archive(owner, user_goals=[_GOAL]), _Failure.TIMED_OUT),
            (
                {"max_memory_mb": 0},
                lambda owner: profile_archive(owner, user_goals=[_GOAL]),
                _Failure.PROCESSING_FAILED,
            ),
        ],
        ids=["too-large", "too-many-activities", "timed-out", "out-of-memory"],
    )
    def test_a_limit_the_archive_runs_into_is_reported_by_its_own_code(
        self, owner, states, storage, monkeypatch, settings, archive, failure
    ):
        _use_config(monkeypatch, **settings)
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, archive(owner))

        _run(owner.id, job, states, storage, key, will_retry=True)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, failure)
        assert "Memory" not in state.model_dump_json()

    def test_a_database_failure_before_the_commit_is_retried_while_attempts_remain(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))
        with committed_sessions() as db:
            db.execute(text("DROP TABLE users_goals CASCADE"))
            db.commit()

        with pytest.raises(Exception, match="users_goals"):
            _run(owner.id, job, states, storage, key, will_retry=True)

        assert states.get(owner.id).status == _Status.QUEUED
        assert storage.list_keys(_AREA, "") == [f"{owner.id}/abc.zip"]

    def test_the_same_failure_on_the_last_attempt_is_final(self, committed_sessions, owner, states, storage):
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))
        with committed_sessions() as db:
            db.execute(text("DROP TABLE users_goals CASCADE"))
            db.commit()

        _run(owner.id, job, states, storage, key, will_retry=False)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        assert storage.list_keys(_AREA, "") == []

    def test_a_failure_after_the_commit_says_files_are_incomplete_and_keeps_the_rows(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        archive = archive_of(
            {
                "data/user.json": [{"username": owner.username, "city": "Faro"}],
                f"user_images/{owner.id}.png": png(90, 8),
            }
        )
        key = _stage(storage, owner.id, archive)
        seen = []

        class Writing(FaultyStorage):
            def __getattr__(self, name):
                if name in ("save", "save_stream"):

                    def fail(*args, **kwargs):
                        seen.append(states.get(owner.id).status)
                        raise OSError("disk full")

                    return fail
                return super().__getattr__(name)

        _run(owner.id, job, states, Writing(storage), key, will_retry=True)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.FILES_INCOMPLETE)
        assert seen == [_Status.WRITING_FILES]
        with committed_sessions() as db:
            assert users_integration.require_user(owner.id, db).city == "Faro"

    def test_a_redelivery_after_a_worker_died_in_the_database_part_runs_again(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        states.set_status(owner.id, job.id, _Status.RUNNING)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))

        _run(owner.id, job, states, storage, key)

        assert states.get(owner.id).status == _Status.SUCCEEDED

    def test_a_redelivery_after_a_worker_died_writing_files_does_not_import_twice(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        states.set_status(owner.id, job.id, _Status.WRITING_FILES)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))

        _run(owner.id, job, states, storage, key)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.FILES_INCOMPLETE)
        assert storage.list_keys(_AREA, "") == []
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 0

    @pytest.mark.parametrize("finished", [_Status.SUCCEEDED, _Status.FAILED])
    def test_a_redelivery_of_a_finished_import_does_nothing_and_drops_the_archive(
        self, committed_sessions, owner, states, storage, finished
    ):
        job = _queued(states, owner.id)
        states.set_status(owner.id, job.id, finished)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))

        _run(owner.id, job, states, storage, key)

        assert states.get(owner.id).status == finished
        assert storage.list_keys(_AREA, "") == []
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 0

    def test_a_superseded_import_leaves_the_newer_imports_state_and_claim(
        self, committed_sessions, platform, owner, storage
    ):
        states = import_state_store.ProfileImportStateStore(platform.state)
        first, second = _supersede(states, platform.state, owner.id)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))

        _run(owner.id, first, states, storage, key)

        assert storage.list_keys(_AREA, "") == []
        assert states.get(owner.id, job_id=second.id).status == _Status.QUEUED
        assert states.get(owner.id, job_id=first.id) is None
        with committed_sessions() as db:
            assert goals_crud.count_user_goals(owner.id, db) == 0
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(owner.id, conflict="held")

    def test_an_archive_outside_the_users_prefix_is_refused_and_left_alone(self, owner, states, storage):
        job = _queued(states, owner.id)
        stranger = uuid.uuid4()
        key = _stage(storage, stranger, profile_archive(owner))

        _run(owner.id, job, states, storage, key)

        assert states.get(owner.id).status == _Status.QUEUED
        assert storage.list_keys(_AREA, "") == [key]

    def test_a_finished_import_whose_archive_cannot_be_deleted_is_still_finished(
        self, committed_sessions, owner, states, storage
    ):
        job = _queued(states, owner.id)
        key = _stage(storage, owner.id, profile_archive(owner, user_goals=[_GOAL]))
        stuck = FaultyStorage(storage, faults={"delete": StorageBackendUnavailableError("busy")})

        _run(owner.id, job, states, stuck, key)

        assert states.get(owner.id).status == _Status.SUCCEEDED
        assert storage.list_keys(_AREA, "") == [key]

    def test_a_missing_archive_fails_the_import(self, owner, states, storage):
        job = _queued(states, owner.id)

        _run(owner.id, job, states, storage, f"{owner.id}/gone.zip")

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)


class TestImportStatus:
    def test_both_running_phases_read_as_running(self, owner, states):
        job = _queued(states, owner.id)

        for phase in (_Status.RUNNING, _Status.WRITING_FILES):
            states.set_status(owner.id, job.id, phase)
            status = job_service.import_status(job, states.get(owner.id))
            assert status.status == "running"


class TestSweepStagedImports:
    def _stage(self, storage, name, *, age_seconds):
        storage.save(_AREA, name, b"zip")
        aged = time.time() - age_seconds
        os.utime(storage._resolve(_AREA, name), (aged, aged))

    def test_removes_only_archives_older_than_the_cutoff(self, storage):
        self._stage(storage, f"{uuid.uuid4()}/old.zip", age_seconds=100_000)
        fresh = f"{uuid.uuid4()}/new.zip"
        self._stage(storage, fresh, age_seconds=0)

        removed = job_service.sweep_staged_imports(storage, 3600)

        assert removed == 1
        assert storage.list_keys(_AREA, "") == [fresh]

    def test_nothing_stale_removes_nothing(self, storage):
        self._stage(storage, f"{uuid.uuid4()}/new.zip", age_seconds=0)

        assert job_service.sweep_staged_imports(storage, 3600) == 0

    def test_one_failing_delete_does_not_stop_the_rest(self, storage):
        stuck, other = f"{uuid.uuid4()}/a.zip", f"{uuid.uuid4()}/b.zip"
        self._stage(storage, stuck, age_seconds=100_000)
        self._stage(storage, other, age_seconds=100_000)
        busy = FaultyStorage(storage, key_faults={("delete", stuck): StorageBackendUnavailableError("busy")})

        removed = job_service.sweep_staged_imports(busy, 3600)

        assert removed == 1
        assert storage.list_keys(_AREA, "") == [stuck]


class TestDiscardStagedImports:
    def test_removes_every_archive_of_the_user_and_only_theirs(self, owner, storage):
        _stage(storage, owner.id, b"zip", "a.zip")
        _stage(storage, owner.id, b"zip", "b.zip")
        theirs = _stage(storage, uuid.uuid4(), b"zip")

        job_service.discard_staged_imports(owner.id, storage)

        assert storage.list_keys(_AREA, "") == [theirs]

    def test_a_listing_failure_is_logged_not_raised(self, owner, storage):
        key = _stage(storage, owner.id, b"zip")
        down = FaultyStorage(storage, faults={"list_keys": StorageBackendUnavailableError("down")})

        job_service.discard_staged_imports(owner.id, down)

        assert storage.list_keys(_AREA, "") == [key]

    def test_a_failed_delete_is_logged_not_raised(self, owner, storage):
        key = _stage(storage, owner.id, b"zip")
        down = FaultyStorage(storage, faults={"delete": StorageBackendUnavailableError("down")})

        job_service.discard_staged_imports(owner.id, down)

        assert storage.list_keys(_AREA, "") == [key]

    def test_an_unexpected_error_propagates(self, owner, storage):
        _stage(storage, owner.id, b"zip")
        broken = FaultyStorage(storage, faults={"delete": RuntimeError("bug")})

        with pytest.raises(RuntimeError, match="bug"):
            job_service.discard_staged_imports(owner.id, broken)


class TestCloseDeadLetteredImport:
    @pytest.mark.parametrize(
        ("status", "failure"),
        [
            (_Status.QUEUED, _Failure.PROCESSING_FAILED),
            (_Status.RUNNING, _Failure.PROCESSING_FAILED),
            (_Status.WRITING_FILES, _Failure.FILES_INCOMPLETE),
        ],
    )
    def test_a_pending_import_is_failed_with_the_reason_its_state_implies(
        self, owner, states, storage, status, failure
    ):
        job = _queued(states, owner.id)
        states.set_status(owner.id, job.id, status)
        key = _stage(storage, owner.id, b"zip")

        job_service.close_dead_lettered_import(_payload(owner.id, job.id, key), states, storage)

        state = states.get(owner.id)
        assert (state.status, state.error_code) == (_Status.FAILED, failure)
        assert storage.list_keys(_AREA, "") == []
        states.begin(owner.id, conflict="held")

    def test_a_superseded_import_leaves_the_newer_imports_state_and_claim(self, platform, owner, storage):
        states = import_state_store.ProfileImportStateStore(platform.state)
        first, second = _supersede(states, platform.state, owner.id)
        key = _stage(storage, owner.id, b"zip")

        job_service.close_dead_lettered_import(_payload(owner.id, first.id, key), states, storage)

        assert states.get(owner.id, job_id=second.id).status == _Status.QUEUED
        assert storage.list_keys(_AREA, "") == []

    def test_an_import_that_already_finished_keeps_its_outcome(self, owner, states, storage):
        job = _queued(states, owner.id)
        states.set_status(owner.id, job.id, _Status.SUCCEEDED, imported={"gears": 1})
        key = _stage(storage, owner.id, b"zip")

        job_service.close_dead_lettered_import(_payload(owner.id, job.id, key), states, storage)

        assert states.get(owner.id).status == _Status.SUCCEEDED
        assert storage.list_keys(_AREA, "") == []
