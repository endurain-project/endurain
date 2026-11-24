"""Account deletions on the real database: accepting, running in batches and passes, retrying, closing and sweeping."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers
import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity.models as activity_models
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.deletion_job_service as job_service
import modules.users.users.deletion_state_store as deletion_state_store
import modules.users.users.events as users_events
import modules.users.users.models as users_models
import modules.users.users.photo_service as users_photo_service
import modules.users.users.subscribers as users_subscribers
from tests._factories.activities import make_activity
from tests._factories.server_settings import edit_mail_settings
from tests._factories.tokens import make_sign_up_token
from tests._factories.users import PASSWORD, make_admin, make_user

_Status = users_constants.DeletionStatus
_Kind = users_constants.DeletionKind.ACCOUNT
_PNG_KEY = ".png"


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


@pytest.fixture
def states(platform):
    return deletion_state_store.UserDeletionStateStore(platform.state)


@pytest.fixture
def deletion_pool(monkeypatch):
    """Replace the module's in-process pool with one of its own, which the test drains before it reads."""
    pool = core_local_pool.BoundedPool("user-deletion-test", workers=1, max_pending=5)
    monkeypatch.setattr(job_service, "_deletion_pool", pool)
    yield pool
    pool.shutdown(wait=True)


@pytest.fixture
def durable(monkeypatch, platform):
    """Run as the durable profile does: the request publishes the work, and the test runs it as a worker would."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    published: list = []
    platform.events.subscribe(users_events.USERS_DELETION_REQUESTED, published.append)
    return published


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def admin(committed_sessions):
    with committed_sessions() as db:
        created = make_admin(db)
        db.commit()
    return created


def _row(committed_sessions, user_id) -> users_models.Users | None:
    with committed_sessions() as db:
        row = db.get(users_models.Users, user_id)
        if row is not None:
            db.expunge(row)
        return row


def _activity_count(committed_sessions, user_id) -> int:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(sa.func.count(activity_models.Activity.id)).where(activity_models.Activity.user_id == user_id)
        )


def _with_activities(committed_sessions, user, count: int) -> None:
    with committed_sessions() as db:
        for _ in range(count):
            make_activity(db, user.id)
        db.commit()


def _queue(committed_sessions, states, user):
    """Mark the account as queued for deletion and claim the job, as a request does; return the job."""
    with committed_sessions() as db:
        users_crud.stage_deletion_request(user.id, db)
        db.commit()
    return states.begin(user.id, _Kind, conflict="held", owner_id=user.id)


def _payload(user, job) -> users_events.DeletionRequestedPayload:
    return users_events.DeletionRequestedPayload(user_id=user.id, job_id=job.id)


def _run(platform, states, user, job, **kwargs) -> bool:
    return job_service.run_deletion(
        _payload(user, job), states, platform.storage, platform.mail, **({"first_pass": False} | kwargs)
    )


def _audit_actions(committed_sessions) -> list[str]:
    with committed_sessions() as db:
        return list(db.scalars(sa.select(AuditLog.action_id).order_by(AuditLog.occurred_at, AuditLog.id)))


def _erasers_with(**replacements):
    users_contributor_registry.register(dataclasses.replace(users_contributor_registry.erasers(), **replacements))


class _Storage:
    """The platform storage with the failures of an unreachable backend arranged on chosen calls."""

    def __init__(self, storage, *, list_keys=None):
        self._storage = storage
        self._list_keys = list_keys

    def __getattr__(self, name):
        if name == "list_keys" and self._list_keys is not None:

            def fail(*_args, **_kwargs):
                raise self._list_keys

            return fail
        return getattr(self._storage, name)


class _Mail:
    """A mail provider whose server refuses the message."""

    def send(self, message):
        raise platform_providers.MailError("refused", kind=platform_providers.MailFailure.OTHER)


class TestRequestDeletion:
    def test_without_durable_jobs_the_work_runs_on_the_pool_and_the_account_is_erased(
        self, committed_sessions, platform, states, deletion_pool, user
    ):
        _with_activities(committed_sessions, user, 3)
        with committed_sessions() as db:
            users_photo_service.store_photo(user.id, _PNG_KEY, _png(), platform.storage, db)

        with committed_sessions() as db:
            result = job_service.request_deletion(
                user.id, user.id, states, platform.storage, platform.mail, db, if_match="*"
            )
        deletion_pool.shutdown(wait=True)

        assert (result.kind, result.status) == (users_constants.DELETION_JOB, _Status.QUEUED)
        assert states.get(user.id, _Kind, job_id=result.id).status == _Status.SUCCEEDED
        assert _row(committed_sessions, user.id) is None
        assert _activity_count(committed_sessions, user.id) == 0
        assert list(platform.storage.list_keys(users_constants.USER_IMAGE_STORAGE_AREA)) == []

    def test_a_durable_request_deactivates_signs_out_marks_and_audits_before_the_worker_runs(
        self, committed_sessions, platform, states, durable, user, sign_in
    ):
        signed_in = sign_in(user)
        with committed_sessions() as db:
            make_sign_up_token(db, user)
            db.commit()
            before = security_generation_integration.current_generation(user.id, db)

        with committed_sessions() as db:
            result = job_service.request_deletion(
                user.id, user.id, states, platform.storage, platform.mail, db, if_match='"1"'
            )

        row = _row(committed_sessions, user.id)
        assert (row.active, row.deactivated_at is not None, row.deletion_requested_at is not None) == (
            False,
            True,
            True,
        )
        with committed_sessions() as db:
            assert (
                db.scalars(
                    sa.select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.user_id == user.id)
                ).all()
                == []
            )
            assert db.scalars(sa.select(sign_up_models.SignUpToken.used)).all() == [True]
            assert security_generation_integration.current_generation(user.id, db) == before + 1
        assert users_audit_actions.USER_DELETE.id in _audit_actions(committed_sessions)
        [event] = durable
        assert (event.payload["user_id"], event.payload["job_id"]) == (str(user.id), str(result.id))
        assert event.source == users_constants.DELETION_SOURCE_API
        assert signed_in.session_id

    def test_a_durable_request_is_erased_by_the_worker_that_runs_the_event(
        self, committed_sessions, platform, states, durable, user
    ):
        _with_activities(committed_sessions, user, 2)
        with committed_sessions() as db:
            job_service.request_deletion(user.id, user.id, states, platform.storage, platform.mail, db, if_match="*")

        users_subscribers.process_deletion_requested_for_event(durable[0])

        assert _row(committed_sessions, user.id) is None
        assert _activity_count(committed_sessions, user.id) == 0

    def test_a_stale_version_is_refused_before_anything_is_queued(
        self, committed_sessions, platform, states, deletion_pool, user
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
            job_service.request_deletion(user.id, user.id, states, platform.storage, platform.mail, db, if_match='"99"')

        row = _row(committed_sessions, user.id)
        assert (row.active, row.deletion_requested_at) == (True, None)
        assert states.get(user.id, _Kind) is None

    def test_a_missing_user_is_not_found(self, committed_sessions, platform, states, deletion_pool):
        with committed_sessions() as db, pytest.raises(core_exceptions.NotFoundError):
            job_service.request_deletion(
                uuid.uuid4(), uuid.uuid4(), states, platform.storage, platform.mail, db, if_match="*"
            )

    def test_the_only_administrator_is_refused_and_stays_active(
        self, committed_sessions, platform, states, deletion_pool, admin
    ):
        with committed_sessions() as db, pytest.raises(core_exceptions.LastAdministratorError):
            job_service.request_deletion(admin.id, admin.id, states, platform.storage, platform.mail, db, if_match="*")

        assert _row(committed_sessions, admin.id).active is True
        assert states.get(admin.id, _Kind) is None

    def test_a_pending_deletion_is_refused_naming_the_running_job_and_the_account_is_untouched(
        self, committed_sessions, platform, states, deletion_pool, user
    ):
        running = states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

        with committed_sessions() as db, pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            job_service.request_deletion(user.id, user.id, states, platform.storage, platform.mail, db, if_match="*")

        assert refused.value.job_id == running.id
        assert _row(committed_sessions, user.id).deletion_requested_at is None

    def test_a_full_local_pool_refuses_before_the_claim_is_taken(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        monkeypatch.setattr(
            job_service, "_deletion_pool", core_local_pool.BoundedPool("full", workers=1, max_pending=0)
        )

        with committed_sessions() as db, pytest.raises(core_local_pool.PoolFullError):
            job_service.request_deletion(user.id, user.id, states, platform.storage, platform.mail, db, if_match="*")

        assert states.get(user.id, _Kind) is None
        assert _row(committed_sessions, user.id).active is True

    def test_a_failure_before_the_job_starts_frees_the_claim(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        class RefusesAtSubmit(core_local_pool.BoundedPool):
            """A pool that had room when asked and lost it before the job was submitted."""

            def submit(self, run, /, *args, **kwargs):
                raise core_local_pool.PoolFullError("taken meanwhile")

        monkeypatch.setattr(job_service, "_deletion_pool", RefusesAtSubmit("race", workers=1, max_pending=1))

        with committed_sessions() as db, pytest.raises(core_local_pool.PoolFullError):
            job_service.request_deletion(user.id, user.id, states, platform.storage, platform.mail, db, if_match="*")

        assert states.get(user.id, _Kind).status == _Status.FAILED
        states.begin(user.id, _Kind, conflict="held", owner_id=user.id)


def _png() -> bytes:
    from tests._helpers import images

    return images.png_with_text()


class TestRequestDeletionByAdministrator:
    @staticmethod
    def _request(committed_sessions, platform, states, store, admin, user, *, password=PASSWORD, if_match='"1"'):
        with committed_sessions() as db:
            return job_service.request_deletion_by_administrator(
                user.id,
                admin.id,
                uuid.uuid4(),
                auth_schema.StepUpVerification(current_password=password),
                store,
                states,
                platform.storage,
                platform.mail,
                db,
                if_match=if_match,
            )

    @pytest.fixture
    def store(self, platform):
        return account_security_integration.get_step_up_attempts(platform.state)

    def test_another_users_account_is_queued_after_the_administrators_step_up_and_the_admin_owns_the_job(
        self, committed_sessions, platform, states, deletion_pool, store, admin, user
    ):
        result = self._request(committed_sessions, platform, states, store, admin, user)
        deletion_pool.shutdown(wait=True)

        assert states.get(user.id, _Kind, job_id=result.id).status == _Status.SUCCEEDED
        assert _row(committed_sessions, user.id) is None

    def test_an_administrator_cannot_delete_their_own_account_here(
        self, committed_sessions, platform, states, deletion_pool, store, admin
    ):
        with pytest.raises(core_exceptions.PermissionDeniedError):
            self._request(committed_sessions, platform, states, store, admin, admin)

        assert _row(committed_sessions, admin.id).active is True

    def test_a_failed_step_up_queues_nothing(
        self, committed_sessions, platform, states, deletion_pool, store, admin, user
    ):
        with pytest.raises(core_exceptions.StepUpFailedError):
            self._request(committed_sessions, platform, states, store, admin, user, password="wrong-password")

        assert _row(committed_sessions, user.id).deletion_requested_at is None
        assert states.get(user.id, _Kind) is None

    def test_a_stale_version_is_refused_after_the_step_up(
        self, committed_sessions, platform, states, deletion_pool, store, admin, user
    ):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._request(committed_sessions, platform, states, store, admin, user, if_match='"99"')

        assert _row(committed_sessions, user.id).deletion_requested_at is None


class TestRunDeletion:
    def test_the_activities_the_photo_the_row_and_the_staged_files_are_erased_and_the_job_succeeds(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        monkeypatch.setattr(users_constants, "DELETION_BATCH_SIZE", 2)
        _with_activities(committed_sessions, user, 5)
        with committed_sessions() as db:
            users_photo_service.store_photo(user.id, _PNG_KEY, _png(), platform.storage, db)
        job = _queue(committed_sessions, states, user)

        assert _run(platform, states, user, job) is False

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.SUCCEEDED
        assert _row(committed_sessions, user.id) is None
        assert _activity_count(committed_sessions, user.id) == 0
        assert list(platform.storage.list_keys(users_constants.USER_IMAGE_STORAGE_AREA)) == []

    def test_another_users_data_is_left_alone(self, committed_sessions, platform, states, user):
        with committed_sessions() as db:
            bystander = make_user(db)
            make_activity(db, bystander.id)
            db.commit()
        job = _queue(committed_sessions, states, user)

        _run(platform, states, user, job)

        assert _row(committed_sessions, bystander.id) is not None
        assert _activity_count(committed_sessions, bystander.id) == 1

    def test_the_photo_is_erased_while_the_row_still_marks_the_deletion(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        with committed_sessions() as db:
            users_photo_service.store_photo(user.id, _PNG_KEY, _png(), platform.storage, db)
        job = _queue(committed_sessions, states, user)
        marked_when_photo_files_go: list[bool] = []
        real_delete = users_photo_service.delete_photo_files

        def record_then_delete(user_id, storage) -> None:
            marked_when_photo_files_go.append(_row(committed_sessions, user_id).deletion_requested_at is not None)
            real_delete(user_id, storage)

        monkeypatch.setattr(users_photo_service, "delete_photo_files", record_then_delete)

        _run(platform, states, user, job)

        assert marked_when_photo_files_go == [True]

    def test_a_row_an_earlier_attempt_already_deleted_is_not_deleted_again(
        self, committed_sessions, platform, states, user
    ):
        job = _queue(committed_sessions, states, user)
        with committed_sessions() as db:
            users_crud.delete_user(user.id, db)
            db.commit()

        assert _run(platform, states, user, job) is False

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.SUCCEEDED

    def test_a_photo_storage_failure_nothing_retries_fails_the_deletion_and_keeps_the_row(
        self, committed_sessions, platform, states, user
    ):
        job = _queue(committed_sessions, states, user)

        result = job_service.run_deletion(
            _payload(user, job),
            states,
            _Storage(platform.storage, list_keys=OSError("storage down")),
            platform.mail,
            first_pass=False,
        )

        assert result is False
        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.FAILED
        assert _row(committed_sessions, user.id) is not None
        states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

    def test_a_failure_a_worker_will_retry_stays_queued_with_the_claim_held_and_raises(
        self, committed_sessions, platform, states, user
    ):
        job = _queue(committed_sessions, states, user)

        with pytest.raises(OSError):
            job_service.run_deletion(
                _payload(user, job),
                states,
                _Storage(platform.storage, list_keys=OSError("storage down")),
                platform.mail,
                first_pass=False,
                will_retry=True,
            )

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

    def test_a_failure_in_the_activity_erasure_nothing_retries_fails_the_deletion(
        self, committed_sessions, platform, states, user
    ):
        def boom(*_args) -> int:
            raise RuntimeError("boom")

        _erasers_with(delete_activities=boom)
        job = _queue(committed_sessions, states, user)

        assert _run(platform, states, user, job) is False

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.FAILED
        assert _row(committed_sessions, user.id) is not None

    def test_running_the_job_again_after_a_failure_finishes_it(self, committed_sessions, platform, states, user):
        _with_activities(committed_sessions, user, 2)
        job = _queue(committed_sessions, states, user)
        original = users_contributor_registry.erasers().delete_activities

        def boom(*_args) -> int:
            raise RuntimeError("boom")

        _erasers_with(delete_activities=boom)
        _run(platform, states, user, job)
        _erasers_with(delete_activities=original)
        retry = states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

        _run(platform, states, user, retry)

        assert states.get(user.id, _Kind, job_id=retry.id).status == _Status.SUCCEEDED
        assert _row(committed_sessions, user.id) is None

    def test_a_deletion_that_is_not_pending_is_skipped(self, committed_sessions, platform, states, user):
        job = _queue(committed_sessions, states, user)
        states.set_status(user.id, _Kind, _Status.SUCCEEDED, job_id=job.id)

        assert _run(platform, states, user, job) is False

        assert _row(committed_sessions, user.id) is not None

    def test_a_superseded_deletion_leaves_the_newer_deletions_state(self, committed_sessions, platform, states, user):
        old = _queue(committed_sessions, states, user)
        states.set_status(user.id, _Kind, _Status.FAILED, job_id=old.id)
        newer = states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

        _run(platform, states, user, old)

        assert states.get(user.id, _Kind, job_id=newer.id).status == _Status.QUEUED
        assert _row(committed_sessions, user.id) is not None

    def test_an_account_reactivated_before_the_job_runs_is_not_erased_and_the_state_is_discarded(
        self, committed_sessions, platform, states, user
    ):
        _with_activities(committed_sessions, user, 1)
        job = _queue(committed_sessions, states, user)
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": True}, db)
            db.commit()

        assert _run(platform, states, user, job) is False

        assert states.get(user.id, _Kind) is None
        assert _row(committed_sessions, user.id) is not None
        assert _activity_count(committed_sessions, user.id) == 1

    def test_a_reactivation_between_batches_stops_the_erasure(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        monkeypatch.setattr(users_constants, "DELETION_BATCH_SIZE", 1)
        _with_activities(committed_sessions, user, 3)
        job = _queue(committed_sessions, states, user)
        real_delete = users_contributor_registry.erasers().delete_activities

        def delete_then_reactivate(user_id, limit, db) -> int:
            deleted = real_delete(user_id, limit, db)
            if deleted:
                users_crud.update_user(user_id, {"active": True}, db)
            return deleted

        _erasers_with(delete_activities=delete_then_reactivate)

        _run(platform, states, user, job)

        assert states.get(user.id, _Kind) is None
        assert _row(committed_sessions, user.id) is not None
        assert _activity_count(committed_sessions, user.id) == 2

    def test_a_reactivation_before_the_row_is_deleted_keeps_the_row(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        job = _queue(committed_sessions, states, user)
        real_delete = users_photo_service.delete_photo_files

        def reactivate_then_delete(user_id, storage) -> None:
            with committed_sessions() as db:
                users_crud.update_user(user_id, {"active": True}, db)
                db.commit()
            real_delete(user_id, storage)

        monkeypatch.setattr(users_photo_service, "delete_photo_files", reactivate_then_delete)

        _run(platform, states, user, job)

        assert _row(committed_sessions, user.id) is not None
        assert states.get(user.id, _Kind) is None


class TestRunDeletionInPasses:
    @pytest.fixture
    def three_batches(self, monkeypatch, committed_sessions, user):
        monkeypatch.setattr(users_constants, "DELETION_BATCH_SIZE", 2)
        _with_activities(committed_sessions, user, 5)

    def test_a_pass_that_spends_its_budget_with_activities_left_asks_to_continue_and_keeps_the_claim(
        self, committed_sessions, platform, states, user, three_batches
    ):
        job = _queue(committed_sessions, states, user)

        assert _run(platform, states, user, job, time_budget=0.0) is True

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.RUNNING
        assert _activity_count(committed_sessions, user.id) == 3
        assert _row(committed_sessions, user.id) is not None
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

    def test_the_next_pass_starts_from_what_is_left_and_finishes_the_erasure(
        self, committed_sessions, platform, states, user, three_batches
    ):
        job = _queue(committed_sessions, states, user)
        _run(platform, states, user, job, time_budget=0.0)

        while _run(platform, states, user, job, time_budget=0.0):
            pass

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.SUCCEEDED
        assert _row(committed_sessions, user.id) is None
        assert _activity_count(committed_sessions, user.id) == 0

    def test_a_pass_that_finishes_inside_its_budget_does_not_continue(
        self, committed_sessions, platform, states, user, three_batches
    ):
        job = _queue(committed_sessions, states, user)

        assert _run(platform, states, user, job, time_budget=3600.0) is False

        assert _row(committed_sessions, user.id) is None

    def test_a_reactivation_between_passes_cancels_the_deletion(
        self, committed_sessions, platform, states, user, three_batches
    ):
        job = _queue(committed_sessions, states, user)
        assert _run(platform, states, user, job, time_budget=0.0) is True
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": True}, db)
            db.commit()

        assert _run(platform, states, user, job, time_budget=0.0) is False

        assert states.get(user.id, _Kind) is None
        assert _activity_count(committed_sessions, user.id) == 3

    @pytest.mark.parametrize(("lease", "expected"), [(300, 100.0), (3000, 1000.0), (30, 30.0)])
    def test_the_pass_budget_is_a_third_of_the_lease_with_a_floor(self, monkeypatch, lease, expected):
        monkeypatch.setattr(core_config.settings, "JOBS_LEASE_SECONDS", lease)

        assert job_service.durable_pass_seconds() == expected


class TestDeadLetter:
    def test_a_dead_lettered_deletion_is_failed_and_its_claim_freed(self, committed_sessions, states, user):
        job = _queue(committed_sessions, states, user)

        job_service.close_dead_lettered_deletion(_payload(user, job), states)

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.FAILED
        states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

    def test_a_superseded_deletion_leaves_the_newer_deletions_state(self, committed_sessions, states, user):
        old = _queue(committed_sessions, states, user)
        states.set_status(user.id, _Kind, _Status.FAILED, job_id=old.id)
        newer = states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

        job_service.close_dead_lettered_deletion(_payload(user, old), states)

        assert states.get(user.id, _Kind, job_id=newer.id).status == _Status.QUEUED

    def test_a_finished_deletion_is_left_as_it_is(self, committed_sessions, states, user):
        job = _queue(committed_sessions, states, user)
        states.set_status(user.id, _Kind, _Status.SUCCEEDED, job_id=job.id)

        job_service.close_dead_lettered_deletion(_payload(user, job), states)

        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.SUCCEEDED


class TestRequeueStalledDeletions:
    @staticmethod
    def _stalled(committed_sessions, user, *, attempts: int = 0) -> None:
        """Queue the account's deletion five hours ago, longer than any live job's claim."""
        with committed_sessions() as db:
            users_crud.stage_deletion_request(user.id, db)
            db.execute(
                sa.update(users_models.Users)
                .where(users_models.Users.id == user.id)
                .values(deletion_requested_at=datetime.now(UTC) - timedelta(hours=5), deletion_attempts=attempts)
            )
            db.commit()

    @staticmethod
    def _sweep(platform, states) -> int:
        return job_service.requeue_stalled_deletions(states, platform.storage, platform.mail, platform.clock)

    def test_a_stalled_deletion_is_queued_again_and_erased(
        self, committed_sessions, platform, states, deletion_pool, user
    ):
        self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 1
        deletion_pool.shutdown(wait=True)

        assert _row(committed_sessions, user.id) is None

    def test_a_deletion_queued_recently_is_not_stalled(self, committed_sessions, platform, states, deletion_pool, user):
        with committed_sessions() as db:
            users_crud.stage_deletion_request(user.id, db)
            db.commit()

        assert self._sweep(platform, states) == 0
        assert states.get(user.id, _Kind) is None

    def test_the_sweep_is_the_recorded_source_and_counts_the_attempt(
        self, committed_sessions, platform, states, durable, user
    ):
        self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 1

        [event] = durable
        assert event.source == users_constants.DELETION_SOURCE_SWEEP
        assert _row(committed_sessions, user.id).deletion_attempts == 1

    def test_the_sweep_pages_through_the_stalled_accounts_by_id(
        self, committed_sessions, monkeypatch, platform, states, durable
    ):
        monkeypatch.setattr(users_constants, "DELETION_SWEEP_BATCH_SIZE", 1)
        with committed_sessions() as db:
            users = [make_user(db) for _ in range(3)]
            db.commit()
        for user in users:
            self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 3
        assert sorted(event.payload["user_id"] for event in durable) == sorted(str(user.id) for user in users)

    def test_a_deletion_a_live_job_holds_is_left_alone(self, committed_sessions, platform, states, durable, user):
        self._stalled(committed_sessions, user)
        states.begin(user.id, _Kind, conflict="held", owner_id=user.id)

        assert self._sweep(platform, states) == 0

        assert durable == []
        assert _row(committed_sessions, user.id).deletion_attempts == 0

    def test_an_account_an_administrator_reactivated_is_not_queued(
        self, committed_sessions, platform, states, durable, user
    ):
        self._stalled(committed_sessions, user)
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": True}, db)
            db.commit()

        assert self._sweep(platform, states) == 0

        assert durable == []

    def test_an_account_reactivated_after_it_was_listed_is_closed_without_an_attempt(
        self, committed_sessions, platform, states, durable, user
    ):
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": False}, db)
            db.commit()
        with committed_sessions() as db:
            users_crud.update_user(user.id, {"active": True}, db)
            db.commit()

        assert job_service._requeue(user.id, states, platform.storage, platform.mail) == 0

        assert states.get(user.id, _Kind).status == _Status.SUCCEEDED
        assert durable == []

    def test_an_account_the_sweep_queued_the_maximum_number_of_times_is_left_for_an_administrator(
        self, committed_sessions, platform, states, durable, user
    ):
        self._stalled(committed_sessions, user, attempts=users_constants.DELETION_SWEEP_MAX_ATTEMPTS)

        assert self._sweep(platform, states) == 0

        assert durable == []

    def test_the_last_automatic_attempt_still_queues_the_deletion(
        self, committed_sessions, platform, states, durable, user
    ):
        self._stalled(committed_sessions, user, attempts=users_constants.DELETION_SWEEP_MAX_ATTEMPTS - 1)

        assert self._sweep(platform, states) == 1

        assert _row(committed_sessions, user.id).deletion_attempts == users_constants.DELETION_SWEEP_MAX_ATTEMPTS

    def test_one_account_that_cannot_be_queued_does_not_stop_the_rest(
        self, committed_sessions, monkeypatch, platform, states
    ):
        class FailsOnce(core_local_pool.BoundedPool):
            """A pool whose first submission fails with something other than being full."""

            failed = False

            def submit(self, run, /, *args, **kwargs):
                if not self.failed:
                    FailsOnce.failed = True
                    raise RuntimeError("cannot start")
                return super().submit(run, *args, **kwargs)

        pool = FailsOnce("flaky", workers=1, max_pending=5)
        monkeypatch.setattr(job_service, "_deletion_pool", pool)
        with committed_sessions() as db:
            users = sorted((make_user(db) for _ in range(2)), key=lambda created: created.id)
            db.commit()
        for user in users:
            self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 1
        pool.shutdown(wait=True)

        assert states.get(users[0].id, _Kind).status == _Status.FAILED
        assert _row(committed_sessions, users[0].id) is not None
        assert _row(committed_sessions, users[1].id) is None

    def test_a_full_pool_stops_the_pass_before_an_attempt_is_spent(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        monkeypatch.setattr(
            job_service, "_deletion_pool", core_local_pool.BoundedPool("full", workers=1, max_pending=0)
        )
        self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 0

        assert _row(committed_sessions, user.id).deletion_attempts == 0
        assert states.get(user.id, _Kind) is None

    def test_a_pool_that_fills_up_after_the_claim_fails_the_job_and_stops_the_pass(
        self, committed_sessions, monkeypatch, platform, states, user
    ):
        class RefusesAtSubmit(core_local_pool.BoundedPool):
            def submit(self, run, /, *args, **kwargs):
                raise core_local_pool.PoolFullError("taken meanwhile")

        monkeypatch.setattr(job_service, "_deletion_pool", RefusesAtSubmit("race", workers=1, max_pending=1))
        self._stalled(committed_sessions, user)

        assert self._sweep(platform, states) == 0

        assert states.get(user.id, _Kind).status == _Status.FAILED


class TestDeletionNotice:
    @pytest.fixture
    def mail_on(self, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(
                db, host="smtp.example.com", port=587, security="starttls", username=None, from_address=None
            )
            db.commit()

    def test_the_first_pass_mails_the_address_on_the_row_before_erasing(
        self, committed_sessions, platform, states, mail_on, user
    ):
        job = _queue(committed_sessions, states, user)

        _run(platform, states, user, job, first_pass=True)

        [message] = platform.mail.outbox
        assert list(message.to) == [user.email]
        assert _row(committed_sessions, user.id) is None

    def test_a_later_delivery_of_the_job_does_not_send_again(self, committed_sessions, platform, states, mail_on, user):
        job = _queue(committed_sessions, states, user)

        _run(platform, states, user, job, first_pass=False)

        assert platform.mail.outbox == []

    def test_a_deletion_the_sweep_queued_again_does_not_send_again(
        self, committed_sessions, platform, states, mail_on, user
    ):
        job = _queue(committed_sessions, states, user)
        with committed_sessions() as db:
            users_crud.record_deletion_attempt(user.id, db)
            db.commit()

        _run(platform, states, user, job, first_pass=True)

        assert platform.mail.outbox == []
        assert _row(committed_sessions, user.id) is None

    def test_without_mail_configured_nothing_is_sent_and_the_deletion_goes_on(
        self, committed_sessions, platform, states, user
    ):
        job = _queue(committed_sessions, states, user)

        _run(platform, states, user, job, first_pass=True)

        assert platform.mail.outbox == []
        assert _row(committed_sessions, user.id) is None

    def test_a_missing_row_sends_nothing_and_the_deletion_goes_on(
        self, committed_sessions, platform, states, mail_on, user
    ):
        job = _queue(committed_sessions, states, user)
        with committed_sessions() as db:
            users_crud.delete_user(user.id, db)
            db.commit()

        _run(platform, states, user, job, first_pass=True)

        assert platform.mail.outbox == []
        assert states.get(user.id, _Kind, job_id=job.id).status == _Status.SUCCEEDED

    def test_a_mail_failure_does_not_stop_the_deletion_and_the_address_is_not_logged(
        self, committed_sessions, caplog, platform, states, mail_on, user
    ):
        job = _queue(committed_sessions, states, user)

        with caplog.at_level("WARNING"):
            job_service.run_deletion(_payload(user, job), states, platform.storage, _Mail(), first_pass=True)

        assert _row(committed_sessions, user.id) is None
        assert user.email not in caplog.text


class TestUnverifiedSignUpPurge:
    def test_the_old_unverified_sign_ups_are_deleted_and_audited_as_the_system(self, committed_sessions):
        from tests._factories.users import make_sign_up

        with committed_sessions() as db:
            stale = make_sign_up(db, created_at=datetime.now(UTC) - timedelta(days=3))
            fresh = make_sign_up(db)
            verified = make_user(db, active=False, deactivated_at=None, email_verified=True)
            db.commit()

        with committed_sessions() as db:
            purged = job_service.stage_unverified_sign_up_purge(datetime.now(UTC) - timedelta(days=1), [], 10, db)
            db.commit()

        assert purged == 1
        assert _row(committed_sessions, stale.id) is None
        assert _row(committed_sessions, fresh.id) is not None
        assert _row(committed_sessions, verified.id) is not None
        with committed_sessions() as db:
            [row] = db.scalars(sa.select(AuditLog).where(AuditLog.action_id == users_audit_actions.USER_PURGE.id))
        assert row.target_id == str(stale.id)

    def test_nothing_to_purge_stages_nothing(self, committed_sessions):
        with committed_sessions() as db:
            assert job_service.stage_unverified_sign_up_purge(datetime.now(UTC), [], 10, db) == 0
