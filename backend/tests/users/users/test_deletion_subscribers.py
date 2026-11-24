"""The durable entry points of a queued account deletion, run against the real database."""

import dataclasses
import uuid
from dataclasses import replace

import pytest
from jasil.events import Event, new_event
from jasil.jobs import ContinueJob
from jasil.jobs.registry import JobHandlerRegistry

import core.config as core_config
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.deletion_state_store as deletion_state_store
import modules.users.users.events as users_events
import modules.users.users.models as users_models
import modules.users.users.subscriber_registry as users_subscriber_registry
import modules.users.users.subscribers as users_subscribers
from tests._factories.activities import make_activity
from tests._factories.users import make_user

_Kind = users_constants.DeletionKind.ACCOUNT
_Status = users_constants.DeletionStatus


@pytest.fixture
def states(_publish_local_platform):
    return deletion_state_store.UserDeletionStateStore(_publish_local_platform.state)


@pytest.fixture
def queued(committed_sessions, states):
    """A user whose deletion is queued, with its job."""
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    with committed_sessions() as db:
        users_crud.stage_deletion_request(user.id, db)
        db.commit()
    return user, states.begin(user.id, _Kind, conflict="held", owner_id=user.id)


def _event(user, job, *, attempt: int = 1, max_attempts: int | None = None, continuation: int = 0) -> Event:
    event = new_event(
        users_events.USERS_DELETION_REQUESTED,
        {"user_id": str(user.id), "job_id": str(job.id)},
        source="test",
        retry_count=attempt,
    )
    return replace(event, max_attempts=max_attempts, continuation_count=continuation)


def _fail_erasing(error: Exception) -> None:
    def fail(*_args) -> int:
        raise error

    users_contributor_registry.register(
        dataclasses.replace(users_contributor_registry.erasers(), delete_activities=fail)
    )


def _row(committed_sessions, user_id):
    with committed_sessions() as db:
        return db.get(users_models.Users, user_id)


class TestDurableHandler:
    def test_a_deletion_that_fails_with_attempts_left_stays_queued_and_asks_to_be_retried(
        self, committed_sessions, states, queued
    ):
        user, job = queued
        _fail_erasing(RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            users_subscribers.process_deletion_requested_for_event(_event(user, job, attempt=1, max_attempts=3))

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.QUEUED
        assert _row(committed_sessions, user.id) is not None

    def test_a_deletion_that_fails_on_its_last_attempt_is_failed_and_not_retried(
        self, committed_sessions, states, queued
    ):
        user, job = queued
        _fail_erasing(RuntimeError("boom"))

        users_subscribers.process_deletion_requested_for_event(_event(user, job, attempt=3, max_attempts=3))

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.FAILED

    def test_a_pass_that_spends_the_durable_budget_with_activities_left_continues_the_same_job(
        self, committed_sessions, monkeypatch, states, queued
    ):
        user, job = queued
        monkeypatch.setattr(users_constants, "DELETION_BATCH_SIZE", 1)
        monkeypatch.setattr(users_constants, "DELETION_PASS_MIN_SECONDS", 0)
        monkeypatch.setattr(core_config.settings, "JOBS_LEASE_SECONDS", 0)
        with committed_sessions() as db:
            for _ in range(3):
                make_activity(db, user.id)
            db.commit()

        with pytest.raises(ContinueJob) as continued:
            users_subscribers.process_deletion_requested_for_event(_event(user, job, max_attempts=3))

        assert continued.value.delay_seconds == 0
        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.RUNNING

    def test_a_reactivated_account_ends_the_job_without_erasing(self, committed_sessions, states, queued):
        user, job = queued
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": True}, db)
            db.commit()

        users_subscribers.process_deletion_requested_for_event(_event(user, job, max_attempts=3))

        assert _row(committed_sessions, user.id) is not None
        assert states.get(user.id, _Kind) is None


class TestDeadLetter:
    def test_a_dead_lettered_deletion_is_closed_so_it_can_be_queued_again(self, states, queued):
        user, job = queued

        users_subscribers.on_deletion_requested_dead_letter(_event(user, job, attempt=3, max_attempts=3), "boom")

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.FAILED
        states.begin(user.id, _Kind, conflict="held", owner_id=user.id)


class TestRegistration:
    def test_the_handler_and_its_dead_letter_callback_are_registered_for_the_event(self):
        registry = JobHandlerRegistry()

        users_subscriber_registry.register_durable_handlers(registry)

        assert registry.subscribers_for(users_events.USERS_DELETION_REQUESTED) == (
            users_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID,
        )
        assert registry.get(users_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID) is not None

    def test_the_subscriber_has_the_stalled_deletion_sweep_as_its_reconciliation_net(self):
        [net] = users_subscriber_registry.DURABLE_SUBSCRIBER_NETS

        assert net.subscriber_id == users_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID
        assert net.backfill.__name__ == "requeue_stalled_deletions"

    def test_an_event_for_an_unknown_user_is_still_parsed_and_skipped_without_a_pending_deletion(self, states):
        event = new_event(
            users_events.USERS_DELETION_REQUESTED,
            {"user_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4())},
            source="test",
            retry_count=1,
        )

        users_subscribers.process_deletion_requested_for_event(replace(event, max_attempts=3))
