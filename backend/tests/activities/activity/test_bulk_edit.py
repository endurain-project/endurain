"""The bulk visibility edit: accepting it, running it on a worker, closing it and what it leaves behind."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import jasil.jobs.registry as jobs_registry
import jasil.settings as jasil_settings
import jasil.testing as jasil_testing
import pytest
from jasil.events import new_event
from sqlalchemy import select, text
from sqlalchemy.exc import DataError, IntegrityError

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity.audit_actions as activity_audit_actions
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_job_service as job_service
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.subscriber_registry as activity_subscriber_registry
import modules.activities.activity.subscribers as activity_subscribers
from tests._factories.activities import DEFAULT_START, make_activity_at
from tests._factories.users import audit_rows_of

_Status = bulk_edit_constants.BulkEditStatus
_Kind = bulk_edit_constants.BulkEditKind.VISIBILITY
_PUBLIC, _PRIVATE = 0, 2


@pytest.fixture
def states(_publish_local_platform):
    return bulk_edit_state_store.ActivityBulkEditStateStore(_publish_local_platform.state)


@pytest.fixture
def library(arrange, owner, other):
    """Three private activities of the owner and one of another user."""
    ids = arrange(lambda db: [make_activity_at(db, owner.id, DEFAULT_START + timedelta(days=n)).id for n in range(3)])
    theirs = arrange(lambda db: make_activity_at(db, other.id, DEFAULT_START).id)
    return ids, theirs


def _visibilities(committed_sessions, user_id) -> list[int]:
    with committed_sessions() as db:
        return list(
            db.scalars(select(activity_models.Activity.visibility).where(activity_models.Activity.user_id == user_id))
        )


def _payload(job_id, user_id, visibility=_PUBLIC):
    return activity_events.VisibilityEditRequestedPayload(user_id=user_id, job_id=job_id, visibility=visibility)


class TestRequest:
    def test_without_durable_jobs_the_edit_runs_on_the_pool_and_every_activity_of_the_owner_changes(
        self, committed_sessions, owner, other, library, states
    ):
        with committed_sessions() as db:
            queued = job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)
        job_service.shutdown_pool(wait=True)

        assert queued.status == _Status.QUEUED
        assert queued.kind == bulk_edit_constants.BULK_EDIT_JOB
        assert _visibilities(committed_sessions, owner.id) == [_PUBLIC] * 3
        assert _visibilities(committed_sessions, other.id) == [_PRIVATE]
        assert states.get(owner.id, _Kind).status == _Status.SUCCEEDED

    def test_each_changed_activity_gets_a_new_version_and_one_update_event(
        self, committed_sessions, owner, library, states, _publish_local_platform
    ):
        delivered: list = []
        _publish_local_platform.events.subscribe(activity_events.ACTIVITY_UPDATED, delivered.append)
        ids, _ = library

        with committed_sessions() as db:
            job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)
        job_service.shutdown_pool(wait=True)

        with committed_sessions() as db:
            versions = set(
                db.scalars(select(activity_models.Activity.version).where(activity_models.Activity.user_id == owner.id))
            )
        assert versions == {2}
        assert sorted(e.payload["activity_id"] for e in delivered) == sorted(str(i) for i in ids)
        assert {e.source for e in delivered} == {bulk_edit_constants.BULK_EDIT_SOURCE}
        assert {tuple(e.payload["changed_fields"]) for e in delivered} == {("visibility",)}

    @pytest.mark.parametrize("durable", [True, False])
    def test_the_request_is_audited_with_the_visibility_and_the_job_writes_no_row_per_activity(
        self, committed_sessions, owner, library, states, monkeypatch, durable
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", durable)

        with committed_sessions() as db:
            job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)
        job_service.shutdown_pool(wait=True)

        with committed_sessions() as db:
            rows = audit_rows_of(db, activity_audit_actions.VISIBILITY_BULK_UPDATE.id)
        [row] = rows
        assert (row.target_type, row.target_id, row.target_owner_id) == ("user", str(owner.id), str(owner.id))
        assert row.details == {"visibility": _PUBLIC}

    def test_with_durable_jobs_the_work_is_queued_in_the_outbox_and_nothing_changes_yet(
        self, committed_sessions, owner, library, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        platform = jasil_testing.install_test_platform(
            tmp_path,
            clock=jasil_testing.FixedClock(datetime.now(UTC)),
            settings=jasil_settings.JasilSettings(
                audit=jasil_settings.AuditSettings(enabled=True), jobs=jasil_settings.JobSettings(enabled=True)
            ),
        )
        activity_subscriber_registry.register_durable_handlers(jobs_registry.registry)
        durable_states = bulk_edit_state_store.ActivityBulkEditStateStore(platform.state)

        with committed_sessions() as db:
            queued = job_service.request_visibility_edit(owner.id, _PUBLIC, durable_states, db)

        assert queued.status == _Status.QUEUED
        assert _visibilities(committed_sessions, owner.id) == [_PRIVATE] * 3
        with committed_sessions() as db:
            outbox = (
                db.execute(
                    text("SELECT payload FROM jasil_event_outbox WHERE event_type = :t"),
                    {"t": activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED},
                )
                .scalars()
                .all()
            )
        assert [(row["user_id"], row["job_id"], row["visibility"]) for row in outbox] == [
            (str(owner.id), str(queued.id), _PUBLIC)
        ]

    def test_a_second_request_while_one_is_pending_is_refused_naming_the_running_job_and_is_not_audited(
        self, committed_sessions, owner, states, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        with committed_sessions() as db:
            first = job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)

        with committed_sessions() as db, pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            job_service.request_visibility_edit(owner.id, _PRIVATE, states, db)

        assert refused.value.job_id == first.id
        with committed_sessions() as db:
            assert len(audit_rows_of(db, activity_audit_actions.VISIBILITY_BULK_UPDATE.id)) == 1

    def test_a_request_that_fails_before_the_job_starts_frees_the_claim_so_it_can_be_made_again(
        self, committed_sessions, owner, states, _publish_local_platform
    ):
        # An audit log partition exists only around the present, so the commit that queues the edit is refused.
        _publish_local_platform.clock.moment = datetime(2020, 1, 1, tzinfo=UTC)

        with committed_sessions() as db, pytest.raises(IntegrityError):
            job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)

        assert states.get(owner.id, _Kind).status == _Status.FAILED
        states.begin(owner.id, _Kind, conflict="x")

    def test_a_request_the_full_pool_cannot_take_is_refused_before_anything_is_claimed(
        self, committed_sessions, owner, states
    ):
        release = threading.Event()
        for _ in range(bulk_edit_constants.BULK_EDIT_POOL_MAX_PENDING):
            job_service._pool.submit(release.wait)
        try:
            with committed_sessions() as db, pytest.raises(core_local_pool.PoolFullError):
                job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)
            assert states.get(owner.id, _Kind) is None
        finally:
            release.set()
            job_service.shutdown_pool(wait=True)


class TestRun:
    def test_it_changes_the_activities_batch_by_batch_and_records_the_outcome(
        self, committed_sessions, owner, library, states, monkeypatch
    ):
        monkeypatch.setattr(bulk_edit_constants, "BULK_EDIT_BATCH_SIZE", 2)
        job = states.begin(owner.id, _Kind, conflict="x")

        job_service.run_visibility_edit(_payload(job.id, owner.id), states)

        assert _visibilities(committed_sessions, owner.id) == [_PUBLIC] * 3
        assert states.get(owner.id, _Kind).status == _Status.SUCCEEDED

    def test_running_it_again_changes_nothing_more(self, committed_sessions, owner, library, states):
        job = states.begin(owner.id, _Kind, conflict="x")
        job_service.run_visibility_edit(_payload(job.id, owner.id), states)
        with committed_sessions() as db:
            before = list(db.scalars(select(activity_models.Activity.version)))

        assert job_service._apply(owner.id, _PUBLIC) == 0
        with committed_sessions() as db:
            assert list(db.scalars(select(activity_models.Activity.version))) == before

    def test_an_edit_that_is_not_pending_is_skipped(self, committed_sessions, owner, library, states):
        job = states.begin(owner.id, _Kind, conflict="x")
        states.set_status(owner.id, _Kind, _Status.SUCCEEDED, job_id=job.id)

        job_service.run_visibility_edit(_payload(job.id, owner.id), states)

        assert _visibilities(committed_sessions, owner.id) == [_PRIVATE] * 3

    def test_an_edit_whose_state_has_expired_is_skipped(self, committed_sessions, owner, library, states):
        job_service.run_visibility_edit(_payload(uuid.uuid4(), owner.id), states)

        assert _visibilities(committed_sessions, owner.id) == [_PRIVATE] * 3

    def test_a_failure_nothing_retries_fails_the_edit_and_frees_the_claim(self, owner, library, states):
        job = states.begin(owner.id, _Kind, conflict="x")

        # A value the integer column cannot hold makes the database refuse the update.
        job_service.run_visibility_edit(_payload(job.id, owner.id, visibility=2**40), states)

        assert states.get(owner.id, _Kind).status == _Status.FAILED
        states.begin(owner.id, _Kind, conflict="x")

    def test_a_failure_a_worker_will_retry_stays_queued_with_its_claim_and_raises(self, owner, library, states):
        job = states.begin(owner.id, _Kind, conflict="x")

        with pytest.raises(DataError):
            job_service.run_visibility_edit(_payload(job.id, owner.id, visibility=2**40), states, will_retry=True)

        assert states.get(owner.id, _Kind).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(owner.id, _Kind, conflict="x")

    def test_an_edit_superseded_by_a_newer_one_leaves_the_newer_one_alone(self, owner, library, states):
        older = states.begin(owner.id, _Kind, conflict="x")
        states.close_pending(owner.id, _Kind, job_id=older.id)
        newer = states.begin(owner.id, _Kind, conflict="x")

        job_service.run_visibility_edit(_payload(older.id, owner.id), states)

        assert states.get(owner.id, _Kind, job_id=newer.id).status == _Status.QUEUED


class TestDeadLetter:
    def test_a_dead_lettered_edit_is_failed_and_its_claim_freed(self, owner, states):
        job = states.begin(owner.id, _Kind, conflict="x")

        job_service.close_dead_lettered_visibility_edit(_payload(job.id, owner.id), states)

        assert states.get(owner.id, _Kind).status == _Status.FAILED
        states.begin(owner.id, _Kind, conflict="x")

    def test_an_edit_that_already_finished_is_left_as_it_is(self, owner, states):
        job = states.begin(owner.id, _Kind, conflict="x")
        states.set_status(owner.id, _Kind, _Status.SUCCEEDED, job_id=job.id)

        job_service.close_dead_lettered_visibility_edit(_payload(job.id, owner.id), states)

        assert states.get(owner.id, _Kind).status == _Status.SUCCEEDED

    def test_a_superseded_edit_leaves_the_newer_one_alone(self, owner, states):
        older = states.begin(owner.id, _Kind, conflict="x")
        states.close_pending(owner.id, _Kind, job_id=older.id)
        newer = states.begin(owner.id, _Kind, conflict="x")

        job_service.close_dead_lettered_visibility_edit(_payload(older.id, owner.id), states)

        assert states.get(owner.id, _Kind, job_id=newer.id).status == _Status.QUEUED


class TestDurableHandlers:
    def test_the_durable_handler_applies_the_edit_from_the_event(self, committed_sessions, owner, library, states):
        job = states.begin(owner.id, _Kind, conflict="x")
        event = new_event(
            activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED,
            _payload(job.id, owner.id).model_dump(mode="json"),
            source="test",
        )

        activity_subscribers.process_visibility_edit_requested_for_event(event)

        assert _visibilities(committed_sessions, owner.id) == [_PUBLIC] * 3
        assert states.get(owner.id, _Kind).status == _Status.SUCCEEDED

    def test_the_dead_letter_handler_closes_the_pending_edit(self, owner, states):
        job = states.begin(owner.id, _Kind, conflict="x")
        event = new_event(
            activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED,
            _payload(job.id, owner.id).model_dump(mode="json"),
            source="test",
        )

        activity_subscribers.on_visibility_edit_requested_dead_letter(event, "boom")

        assert states.get(owner.id, _Kind).status == _Status.FAILED


class TestPool:
    def test_the_pool_can_be_shut_down_through_the_surface_and_takes_the_next_edit_afterwards(
        self, committed_sessions, owner, library, states
    ):
        activity_integration.shutdown_bulk_edit_pool()

        with committed_sessions() as db:
            job_service.request_visibility_edit(owner.id, _PUBLIC, states, db)
        job_service.shutdown_pool(wait=True)

        assert _visibilities(committed_sessions, owner.id) == [_PUBLIC] * 3


class TestReadingTheJob:
    def test_the_current_job_reads_as_its_status_and_a_superseded_one_as_nothing(
        self, owner, states, _publish_local_platform
    ):
        older = states.begin(owner.id, _Kind, conflict="x")
        assert activity_integration.read_bulk_edit_job(older, _publish_local_platform.state).status == _Status.QUEUED

        states.close_pending(owner.id, _Kind, job_id=older.id)
        states.begin(owner.id, _Kind, conflict="x")

        assert activity_integration.read_bulk_edit_job(older, _publish_local_platform.state) is None
