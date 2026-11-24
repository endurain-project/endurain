"""The gear deletion job on the real database: accepting, running in batches, retrying and closing a deletion."""

import dataclasses
import uuid

import jasil.events as jasil_events
import pytest
from jasil.jobs.registry import JobHandlerRegistry
from sqlalchemy import select

import core.attempt_state as core_attempt_state
import core.config as core_config
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.local_pool as core_local_pool
import modules.activities.activity.models as activity_models
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.deletion_job_service as job_service
import modules.gears.gear.deletion_state_store as deletion_state_store
import modules.gears.gear.events as gears_events
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear.subscriber_registry as gear_subscriber_registry
import modules.gears.gear.subscribers as gears_subscribers
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_Status = core_job_status.JobState


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def state(_publish_local_platform):
    return _publish_local_platform.state


@pytest.fixture
def states(state):
    return deletion_state_store.GearDeletionStateStore(state)


@pytest.fixture
def deletion_pool(monkeypatch):
    """Replace the module's in-process pool with one of its own, which the test drains before it reads."""
    pool = core_local_pool.BoundedPool("gear-deletion-test", workers=1, max_pending=2)
    monkeypatch.setattr(job_service, "_pool", pool)
    yield pool
    pool.shutdown(wait=True)


def _gear_with_activities(committed_sessions, owner, count: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Commit a gear carried by ``count`` activities; return its id and theirs."""
    with committed_sessions() as db:
        gear = make_gear(db, owner.id)
        ids = [make_activity(db, owner.id, gear_id=gear.id).id for _ in range(count)]
        db.commit()
    return gear.id, ids


def _stored_gear(committed_sessions, owner, gear_id):
    with committed_sessions() as db:
        return gear_crud.get_gear_user_by_id(owner.id, gear_id, db)


def _assigned(committed_sessions) -> dict[uuid.UUID, uuid.UUID | None]:
    with committed_sessions() as db:
        return dict(db.execute(select(activity_models.Activity.id, activity_models.Activity.gear_id)).all())


def _payload(owner, gear_id, job_id) -> gears_events.DeletionRequestedPayload:
    return gears_events.DeletionRequestedPayload(user_id=owner.id, gear_id=gear_id, job_id=job_id)


def _supersede(states, state, owner, gear_id):
    """Free the running deletion's claim as an expiry would, then begin a newer one; return the newer job."""
    state.delete(core_attempt_state.key("gears", "deletion:claim", str(gear_id)))
    return states.begin(gear_id, owner.id, conflict="x")


def _fail_unassigning(error: Exception) -> None:
    """Make the activities side of a deletion raise, as a database or provider failure would."""

    def clear(*_args):
        raise error

    gears_contributor_registry.register(
        dataclasses.replace(gears_contributor_registry.readers(), clear_activities_gear=clear)
    )


class TestRequestGearDeletion:
    def test_without_durable_jobs_the_work_runs_on_the_pool_and_the_gear_is_deleted(
        self, committed_sessions, owner, states, deletion_pool
    ):
        gear_id, ids = _gear_with_activities(committed_sessions, owner, 3)

        with committed_sessions() as db:
            result = job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match='"1"')
        deletion_pool.shutdown(wait=True)

        assert (result.kind, result.status) == (gears_constants.DELETION_JOB, _Status.QUEUED)
        assert states.get(gear_id).status == _Status.SUCCEEDED
        assert _stored_gear(committed_sessions, owner, gear_id) is None
        assert _assigned(committed_sessions) == dict.fromkeys(ids)

    def test_a_durable_request_publishes_the_work_and_a_worker_run_deletes_the_gear(
        self, committed_sessions, monkeypatch, owner, states, _publish_local_platform
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        published: list = []
        _publish_local_platform.events.subscribe(gears_events.GEAR_DELETION_REQUESTED, published.append)
        gear_id, ids = _gear_with_activities(committed_sessions, owner, 2)

        with committed_sessions() as db:
            result = job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match='"1"')

        assert states.get(gear_id).status == _Status.QUEUED
        [event] = published
        assert event.payload["gear_id"] == str(gear_id)
        assert event.payload["job_id"] == str(result.id)
        assert _stored_gear(committed_sessions, owner, gear_id) is not None
        gears_subscribers.process_deletion_requested_for_event(event)
        assert states.get(gear_id).status == _Status.SUCCEEDED
        assert _stored_gear(committed_sessions, owner, gear_id) is None
        assert _assigned(committed_sessions) == dict.fromkeys(ids)

    def test_a_stale_version_is_refused_before_anything_is_queued(self, committed_sessions, owner, states):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)

        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match='"99"')

        assert states.get(gear_id) is None

    def test_a_foreign_or_missing_gear_is_not_found_before_anything_is_queued(self, committed_sessions, owner, states):
        with committed_sessions() as db:
            stranger = make_user(db)
            db.commit()
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)

        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            job_service.request_gear_deletion(gear_id, stranger.id, states, db, if_match="*")
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            job_service.request_gear_deletion(uuid.uuid4(), owner.id, states, db, if_match="*")

        assert states.get(gear_id) is None

    def test_a_pending_deletion_is_refused_naming_the_running_job(self, committed_sessions, owner, states):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)
        running = states.begin(gear_id, owner.id, conflict="x")

        with committed_sessions() as db, pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match="*")

        assert refused.value.job_id == running.id

    def test_a_full_pool_refuses_before_the_claim_is_taken(self, committed_sessions, monkeypatch, owner, states):
        monkeypatch.setattr(job_service, "_pool", core_local_pool.BoundedPool("full", workers=1, max_pending=0))
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)

        with committed_sessions() as db, pytest.raises(core_local_pool.PoolFullError):
            job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match="*")

        assert states.get(gear_id) is None

    def test_a_failure_before_the_job_starts_frees_the_claim(self, committed_sessions, monkeypatch, owner, states):
        class RefusesAtSubmit(core_local_pool.BoundedPool):
            """A pool that had room when asked and lost it before the job was submitted."""

            def submit(self, run, /, *args, **kwargs):
                raise core_local_pool.PoolFullError("taken meanwhile")

        monkeypatch.setattr(job_service, "_pool", RefusesAtSubmit("race", workers=1, max_pending=1))
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)

        with committed_sessions() as db, pytest.raises(core_local_pool.PoolFullError):
            job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match="*")

        assert states.get(gear_id).status == _Status.FAILED
        states.begin(gear_id, owner.id, conflict="x")


class TestApply:
    def test_the_gear_is_unassigned_across_batches_and_deleted(self, committed_sessions, monkeypatch, owner):
        monkeypatch.setattr(gears_constants, "DELETION_BATCH_SIZE", 2)
        gear_id, ids = _gear_with_activities(committed_sessions, owner, 5)
        with committed_sessions() as db:
            versions = dict(db.execute(select(activity_models.Activity.id, activity_models.Activity.version)).all())

        unassigned, deleted = job_service._apply(owner.id, gear_id)

        assert deleted is True
        # The batches take two, two and one; the last one is short, so nothing is left for the final transaction.
        assert unassigned == 5
        assert _stored_gear(committed_sessions, owner, gear_id) is None
        with committed_sessions() as db:
            rows = db.execute(
                select(activity_models.Activity.id, activity_models.Activity.gear_id, activity_models.Activity.version)
            ).all()
        assert {row.id for row in rows} == set(ids)
        assert all(row.gear_id is None and row.version == versions[row.id] + 1 for row in rows)

    def test_running_the_job_again_after_the_gear_is_gone_succeeds_without_changes(
        self, committed_sessions, monkeypatch, owner
    ):
        monkeypatch.setattr(gears_constants, "DELETION_BATCH_SIZE", 2)
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 3)
        job_service._apply(owner.id, gear_id)

        assert job_service._apply(owner.id, gear_id) == (0, False)


class TestRunGearDeletion:
    def test_it_unassigns_the_activities_deletes_the_gear_and_records_success(self, committed_sessions, owner, states):
        gear_id, ids = _gear_with_activities(committed_sessions, owner, 3)
        job = states.begin(gear_id, owner.id, conflict="x")

        job_service.run_gear_deletion(_payload(owner, gear_id, job.id), states)

        assert states.get(gear_id).status == _Status.SUCCEEDED
        assert _stored_gear(committed_sessions, owner, gear_id) is None
        assert _assigned(committed_sessions) == dict.fromkeys(ids)

    def test_a_gear_that_is_already_gone_ends_as_succeeded(self, owner, states):
        gear_id = uuid.uuid4()
        job = states.begin(gear_id, owner.id, conflict="x")

        job_service.run_gear_deletion(_payload(owner, gear_id, job.id), states)

        assert states.get(gear_id).status == _Status.SUCCEEDED

    def test_a_deletion_that_is_not_pending_is_skipped(self, committed_sessions, owner, states):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 1)

        job_service.run_gear_deletion(_payload(owner, gear_id, uuid.uuid4()), states)

        assert _stored_gear(committed_sessions, owner, gear_id) is not None
        assert set(_assigned(committed_sessions).values()) == {gear_id}

    def test_a_failure_nothing_retries_fails_the_deletion_and_frees_the_claim(self, committed_sessions, owner, states):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 1)
        job = states.begin(gear_id, owner.id, conflict="x")
        _fail_unassigning(RuntimeError("boom"))

        job_service.run_gear_deletion(_payload(owner, gear_id, job.id), states)

        assert states.get(gear_id).status == _Status.FAILED
        assert _stored_gear(committed_sessions, owner, gear_id) is not None
        states.begin(gear_id, owner.id, conflict="x")

    def test_a_failure_a_worker_will_retry_stays_queued_and_raises(self, committed_sessions, owner, states):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 1)
        job = states.begin(gear_id, owner.id, conflict="x")
        _fail_unassigning(RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            job_service.run_gear_deletion(_payload(owner, gear_id, job.id), states, will_retry=True)

        assert states.get(gear_id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(gear_id, owner.id, conflict="x")

    def test_running_a_superseded_deletion_leaves_the_newer_one_alone(self, committed_sessions, owner, states, state):
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 1)
        old = states.begin(gear_id, owner.id, conflict="x")
        new = _supersede(states, state, owner, gear_id)

        job_service.run_gear_deletion(_payload(owner, gear_id, old.id), states)

        assert _stored_gear(committed_sessions, owner, gear_id) is not None
        assert states.get(gear_id, job_id=new.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(gear_id, owner.id, conflict="x")


class TestDeadLetter:
    def test_a_dead_lettered_deletion_is_failed_and_its_claim_freed(self, owner, states):
        gear_id = uuid.uuid4()
        job = states.begin(gear_id, owner.id, conflict="x")

        job_service.close_dead_lettered_deletion(_payload(owner, gear_id, job.id), states)

        assert states.get(gear_id).status == _Status.FAILED
        states.begin(gear_id, owner.id, conflict="x")

    def test_a_finished_deletion_is_left_alone(self, owner, states):
        gear_id = uuid.uuid4()
        job = states.begin(gear_id, owner.id, conflict="x")
        states.set_status(gear_id, job.id, _Status.SUCCEEDED)

        job_service.close_dead_lettered_deletion(_payload(owner, gear_id, job.id), states)

        assert states.get(gear_id).status == _Status.SUCCEEDED

    def test_a_superseded_deletion_leaves_the_newer_one_alone(self, owner, states, state):
        gear_id = uuid.uuid4()
        old = states.begin(gear_id, owner.id, conflict="x")
        new = _supersede(states, state, owner, gear_id)

        job_service.close_dead_lettered_deletion(_payload(owner, gear_id, old.id), states)

        assert states.get(gear_id, job_id=new.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(gear_id, owner.id, conflict="x")


class TestWorkerWiring:
    @staticmethod
    def _event(owner, gear_id, job_id, *, retry_count: int, max_attempts: int) -> jasil_events.Event:
        return jasil_events.Event(
            event_id=str(uuid.uuid4()),
            event_type=gears_events.GEAR_DELETION_REQUESTED,
            source="test",
            timestamp="2026-01-01T00:00:00+00:00",
            payload={"user_id": owner.id, "gear_id": gear_id, "job_id": job_id},
            retry_count=retry_count,
            max_attempts=max_attempts,
        )

    def test_the_worker_resolves_the_handler_and_runs_the_deletion(self, committed_sessions, owner, states):
        registry = JobHandlerRegistry()
        gear_subscriber_registry.register_durable_handlers(registry)
        gear_id, _ = _gear_with_activities(committed_sessions, owner, 2)
        job = states.begin(gear_id, owner.id, conflict="x")

        handler = registry.get(gears_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID)
        handler(self._event(owner, gear_id, job.id, retry_count=1, max_attempts=3))

        assert states.get(gear_id).status == _Status.SUCCEEDED
        assert _stored_gear(committed_sessions, owner, gear_id) is None

    def test_a_dead_lettered_job_closes_the_deletion_so_it_can_be_queued_again(self, owner, states):
        registry = JobHandlerRegistry()
        gear_subscriber_registry.register_durable_handlers(registry)
        gear_id = uuid.uuid4()
        job = states.begin(gear_id, owner.id, conflict="x")

        on_dead_letter = registry.dead_letter_callback(gears_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID)
        on_dead_letter(self._event(owner, gear_id, job.id, retry_count=3, max_attempts=3), "boom")

        assert states.get(gear_id).status == _Status.FAILED
        states.begin(gear_id, owner.id, conflict="x")


class TestReadDeletionJob:
    def test_a_job_reads_its_status_until_a_newer_deletion_supersedes_it(self, owner, states, state):
        gear_id = uuid.uuid4()
        old = states.begin(gear_id, owner.id, conflict="x")

        assert gear_integration.read_deletion_job(old, state).status == _Status.QUEUED
        _supersede(states, state, owner, gear_id)
        assert gear_integration.read_deletion_job(old, state) is None


def test_shutting_the_pool_down_leaves_it_able_to_take_the_next_deletion(
    committed_sessions, owner, states, deletion_pool
):
    gear_integration.shutdown_deletion_pool()
    gear_id, _ = _gear_with_activities(committed_sessions, owner, 0)

    with committed_sessions() as db:
        job_service.request_gear_deletion(gear_id, owner.id, states, db, if_match="*")
    deletion_pool.shutdown(wait=True)

    assert states.get(gear_id).status == _Status.SUCCEEDED
