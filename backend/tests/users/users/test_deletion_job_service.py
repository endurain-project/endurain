"""Tests for users.deletion_job_service: accepting, running and closing account deletions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.users.users.constants as users_constants
import modules.users.users.deletion_job_service as job_service
import modules.users.users.deletion_state_store as deletion_state_store
import modules.users.users.events as users_events

_MODULE = "modules.users.users.deletion_job_service"
_Status = users_constants.DeletionStatus
_Kind = users_constants.DeletionKind.ACCOUNT


@pytest.fixture
def states():
    return deletion_state_store.UserDeletionStateStore(MemoryState())


@pytest.fixture
def mock_db():
    return MagicMock()


def _payload(user_id: int = 1) -> users_events.DeletionRequestedPayload:
    return users_events.DeletionRequestedPayload(user_id=user_id)


def _repeat_last(values):
    """Yield each value once, then the last one for every further call."""
    items = iter(values)
    last = values[-1]

    def _next(*_args, **_kwargs):
        nonlocal last
        last = next(items, last)
        return last

    return _next


class TestRequestDeletion:
    def _request(self, states, db, *, jobs_enabled, identity=None):
        identity = identity or MagicMock()
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=jobs_enabled)),
            patch(
                f"{_MODULE}.account_security_integration.delete_all_user_sessions",
                side_effect=lambda user_id, db: identity.delete_all_user_sessions(user_id),
            ),
            patch(f"{_MODULE}.sign_up_tokens_integration.revoke_pending_tokens") as revoke_tokens,
            patch(f"{_MODULE}.users_service") as users_service,
            patch(f"{_MODULE}.users_crud") as users_crud,
            patch(f"{_MODULE}.users_event_publishers") as publishers,
            patch(f"{_MODULE}._deletion_pool") as pool,
        ):
            result = job_service.request_deletion(1, states, MagicMock(), db, if_match='"1"')
        self.revoke_tokens = revoke_tokens
        return result, identity, users_service, users_crud, publishers, pool

    def test_a_durable_deletion_signs_out_deactivates_and_publishes(self, states, mock_db):
        result, identity, users_service, users_crud, publishers, pool = self._request(
            states, mock_db, jobs_enabled=True
        )

        assert result.status == _Status.QUEUED
        users_service.require_deletable_user.assert_called_once_with(1, mock_db, if_match='"1"')
        identity.delete_all_user_sessions.assert_called_once_with(1)
        users_crud.stage_deletion_request.assert_called_once_with(1, mock_db)
        # A verification link issued before the deletion must not reactivate the account.
        self.revoke_tokens.assert_called_once_with(1, mock_db)
        publishers.publish_deletion_requested.assert_called_once_with(
            1, mock_db, commit=mock_db.commit, source=users_constants.DELETION_SOURCE_API
        )
        pool.submit.assert_not_called()
        assert states.get(1, _Kind).status == _Status.QUEUED

    def test_without_durable_jobs_the_commit_precedes_the_pool_submit(self, states, mock_db):
        _, _, _, _, publishers, pool = self._request(states, mock_db, jobs_enabled=False)

        pool.require_capacity.assert_called_once_with()
        mock_db.commit.assert_called_once_with()
        pool.submit.assert_called_once()
        publishers.publish_deletion_requested.assert_not_called()

    def test_a_pending_deletion_is_refused_without_touching_the_account(self, states, mock_db):
        states.begin(1, _Kind)
        identity = MagicMock()

        with pytest.raises(core_exceptions.ConflictError):
            self._request(states, mock_db, jobs_enabled=True, identity=identity)

        identity.delete_all_user_sessions.assert_not_called()

    def test_a_failure_before_the_job_starts_frees_the_claim(self, states, mock_db):
        identity = MagicMock()
        identity.delete_all_user_sessions.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            self._request(states, mock_db, jobs_enabled=True, identity=identity)

        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True

    def test_a_full_local_pool_refuses_before_the_claim_is_taken(self, states, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_MODULE}.users_service"),
            patch(f"{_MODULE}._deletion_pool") as pool,
        ):
            pool.require_capacity.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                job_service.request_deletion(1, states, MagicMock(), mock_db, if_match='"1"')

        assert states.get(1, _Kind) is None

    def test_the_only_administrator_is_refused_first(self, states, mock_db):
        identity = MagicMock()
        with (
            patch(f"{_MODULE}.users_service") as users_service,
            patch(f"{_MODULE}.users_crud") as users_crud,
        ):
            users_service.require_deletable_user.side_effect = core_exceptions.ConflictError("only admin")
            with pytest.raises(core_exceptions.ConflictError):
                job_service.request_deletion(1, states, MagicMock(), mock_db, if_match='"1"')

        identity.delete_all_user_sessions.assert_not_called()
        users_crud.stage_deletion_request.assert_not_called()
        assert states.get(1, _Kind) is None


class TestRequestDeletionByAdministrator:
    def test_an_administrator_cannot_delete_their_own_account_without_step_up(self, states, mock_db):
        with patch(f"{_MODULE}.request_deletion") as request, pytest.raises(core_exceptions.PermissionDeniedError):
            job_service.request_deletion_by_administrator(1, 1, states, MagicMock(), mock_db, if_match='"1"')

        request.assert_not_called()

    def test_another_users_account_is_queued(self, states, mock_db):
        storage = MagicMock()
        with patch(f"{_MODULE}.request_deletion") as request:
            result = job_service.request_deletion_by_administrator(1, 9, states, storage, mock_db, if_match='"4"')

        request.assert_called_once_with(1, states, storage, mock_db, if_match='"4"')
        assert result is request.return_value

    def test_a_deletion_that_races_past_the_version_check_is_a_precondition_failure(self, states, mock_db):
        with (
            patch(f"{_MODULE}.request_deletion", side_effect=StaleDataError("moved")),
            patch(f"{_MODULE}.users_crud") as users_crud,
        ):
            users_crud.get_user_by_id.return_value = MagicMock()
            with pytest.raises(core_exceptions.PreconditionFailedError):
                job_service.request_deletion_by_administrator(1, 9, states, MagicMock(), mock_db, if_match='"4"')


class TestRunDeletion:
    def _run(
        self,
        states,
        *,
        batches,
        row_exists=True,
        delete_error=None,
        photo_error=None,
        will_retry=False,
        cancelled=(False,),
    ):
        erasers = MagicMock()
        erasers.delete_activities.side_effect = [*batches, 0] if delete_error is None else delete_error
        with (
            patch(f"{_MODULE}.core_database.SessionLocal") as session_local,
            patch(f"{_MODULE}.users_contributor_registry.erasers", return_value=erasers),
            patch(f"{_MODULE}.users_crud") as users_crud,
            patch(f"{_MODULE}.users_photo_service") as photos,
        ):
            users_crud.get_user_by_id.return_value = MagicMock() if row_exists else None
            users_crud.is_deletion_cancelled.side_effect = _repeat_last(cancelled)
            photos.delete_photo_files.side_effect = photo_error
            storage = MagicMock()
            job_service.run_deletion(_payload(), states, storage, will_retry=will_retry)
        return erasers, users_crud, photos, session_local, storage

    def test_erases_in_batches_then_the_photo_then_the_row_then_the_staged_files(self, states):
        states.begin(1, _Kind)

        erasers, users_crud, photos, session_local, storage = self._run(states, batches=[100, 40])

        assert erasers.delete_activities.call_count == 3
        assert erasers.delete_activities.call_args.args[:2] == (1, users_constants.DELETION_BATCH_SIZE)
        users_crud.replace_photo_key.assert_called_once_with(1, None, session_local.return_value.__enter__.return_value)
        photos.delete_photo_files.assert_called_once_with(1, storage)
        users_crud.delete_user.assert_called_once()
        erasers.delete_staged_files.assert_called_once_with(1, storage)
        assert states.get(1, _Kind).status == _Status.COMPLETED
        # Every batch, the cleared photo reference and the row commit in a transaction of their own.
        assert session_local.return_value.__enter__.return_value.commit.call_count == 5

    def test_the_photo_is_erased_while_the_row_still_marks_the_deletion(self, states):
        """The row is the deletion's record: a photo erased after it went could not be retried."""
        states.begin(1, _Kind)
        order: list[str] = []
        with patch(f"{_MODULE}.users_photo_service") as photos, patch(f"{_MODULE}.users_crud") as users_crud:
            photos.delete_photo_files.side_effect = lambda *_: order.append("photo")
            users_crud.delete_user.side_effect = lambda *_: order.append("row")
            users_crud.is_deletion_cancelled.return_value = False
            with (
                patch(f"{_MODULE}.core_database.SessionLocal"),
                patch(f"{_MODULE}.users_contributor_registry.erasers") as erasers,
            ):
                erasers.return_value.delete_activities.return_value = 0
                job_service.run_deletion(_payload(), states, MagicMock())

        assert order == ["photo", "row"]

    def test_a_row_an_earlier_attempt_deleted_is_not_deleted_again(self, states):
        states.begin(1, _Kind)

        _, users_crud, photos, _, storage = self._run(states, batches=[], row_exists=False)

        users_crud.delete_user.assert_not_called()
        users_crud.replace_photo_key.assert_not_called()
        photos.delete_photo_files.assert_called_once_with(1, storage)
        assert states.get(1, _Kind).status == _Status.COMPLETED

    def test_a_photo_storage_failure_nothing_retries_fails_the_deletion_and_keeps_the_row(self, states):
        """A deletion is only complete once the photo is gone; the kept row lets the sweep queue it again."""
        states.begin(1, _Kind)

        _, users_crud, _, _, _ = self._run(states, batches=[], photo_error=OSError("storage down"))

        users_crud.delete_user.assert_not_called()
        assert states.get(1, _Kind).status == _Status.FAILED

    def test_a_photo_storage_failure_a_worker_will_retry_stays_queued_and_raises(self, states):
        states.begin(1, _Kind)

        with pytest.raises(OSError):
            self._run(states, batches=[], photo_error=OSError("storage down"), will_retry=True)

        assert states.get(1, _Kind).status == _Status.QUEUED

    def test_a_deletion_that_is_not_pending_is_skipped(self, states):
        erasers, users_crud, _, _, _ = self._run(states, batches=[])

        erasers.delete_activities.assert_not_called()
        users_crud.delete_user.assert_not_called()

    def test_a_reactivated_account_is_not_erased(self, states):
        states.begin(1, _Kind)

        erasers, users_crud, photos, _, _ = self._run(states, batches=[100], cancelled=(True,))

        erasers.delete_activities.assert_not_called()
        users_crud.delete_user.assert_not_called()
        photos.delete_photo_files.assert_not_called()
        # Nothing is left for the status route to report, and a later deletion can be queued.
        assert states.get(1, _Kind) is None
        assert states.begin(1, _Kind) is True

    def test_a_reactivation_between_batches_stops_the_erasure(self, states):
        states.begin(1, _Kind)

        erasers, users_crud, photos, _, _ = self._run(states, batches=[100, 100], cancelled=(False, True))

        assert erasers.delete_activities.call_count == 1
        users_crud.delete_user.assert_not_called()
        photos.delete_photo_files.assert_not_called()
        assert states.get(1, _Kind) is None

    def test_a_reactivation_before_the_row_is_deleted_keeps_the_row(self, states):
        states.begin(1, _Kind)

        erasers, users_crud, photos, _, _ = self._run(states, batches=[], cancelled=(False, True))

        erasers.delete_activities.assert_called_once()
        users_crud.delete_user.assert_not_called()
        photos.delete_photo_files.assert_not_called()
        assert states.get(1, _Kind) is None

    def test_a_failure_nothing_retries_fails_the_deletion_and_frees_the_claim(self, states):
        states.begin(1, _Kind)

        _, users_crud, photos, _, _ = self._run(states, batches=[], delete_error=RuntimeError("boom"))

        users_crud.delete_user.assert_not_called()
        photos.delete_photo_files.assert_not_called()
        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True

    def test_a_failure_a_worker_will_retry_stays_queued_and_raises(self, states):
        states.begin(1, _Kind)

        with pytest.raises(RuntimeError):
            self._run(states, batches=[], delete_error=RuntimeError("boom"), will_retry=True)

        assert states.get(1, _Kind).status == _Status.QUEUED
        assert states.begin(1, _Kind) is False


class TestStatusAndDeadLetter:
    def test_status_is_not_found_when_none_is_recorded(self, states):
        with pytest.raises(core_exceptions.NotFoundError):
            job_service.get_deletion_status(1, states)

    def test_status_reports_the_recorded_state(self, states):
        states.begin(1, _Kind)

        assert job_service.get_deletion_status(1, states).status == _Status.QUEUED

    def test_a_dead_lettered_deletion_is_failed_and_its_claim_freed(self, states):
        states.begin(1, _Kind)

        job_service.close_dead_lettered_deletion(_payload(), states)

        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True

    def test_a_finished_deletion_is_left_as_it_is(self, states):
        states.begin(1, _Kind)
        states.set_status(1, _Kind, _Status.COMPLETED)

        job_service.close_dead_lettered_deletion(_payload(), states)

        assert states.get(1, _Kind).status == _Status.COMPLETED


class TestRequeueStalledDeletions:
    def _sweep(self, states, pages, *, attempts=1, jobs_enabled=True, publish_error=None):
        clock = MagicMock()
        clock.now.return_value = datetime(2026, 1, 1, tzinfo=UTC)
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=jobs_enabled)),
            patch(f"{_MODULE}.core_database.SessionLocal"),
            patch(f"{_MODULE}.users_crud") as users_crud,
            patch(f"{_MODULE}.users_event_publishers") as publishers,
            patch(f"{_MODULE}._deletion_pool") as pool,
        ):
            users_crud.list_stalled_deletion_ids.side_effect = [*pages, []]
            users_crud.record_deletion_attempt.return_value = attempts
            publishers.publish_deletion_requested.side_effect = publish_error
            queued = job_service.requeue_stalled_deletions(states, MagicMock(), clock)
        return queued, users_crud, publishers, pool

    def test_queues_each_stalled_deletion_again_with_the_sweep_as_source(self, states):
        queued, users_crud, publishers, _ = self._sweep(states, [[1, 2]])

        assert queued == 2
        assert [c.args[0] for c in publishers.publish_deletion_requested.call_args_list] == [1, 2]
        assert publishers.publish_deletion_requested.call_args.kwargs["source"] == users_constants.DELETION_SOURCE_SWEEP
        cutoff = users_crud.list_stalled_deletion_ids.call_args_list[0].args[0]
        assert cutoff == datetime(2026, 1, 1, tzinfo=UTC) - timedelta(
            seconds=users_constants.DELETION_STALL_AFTER_SECONDS
        )

    def test_pages_through_the_table_by_id(self, states):
        _, users_crud, _, _ = self._sweep(states, [[1, 2], [3]])

        assert [c.args[2] for c in users_crud.list_stalled_deletion_ids.call_args_list] == [0, 2, 3]

    def test_a_deletion_a_live_job_holds_is_left_alone(self, states):
        states.begin(1, _Kind)

        queued, users_crud, publishers, _ = self._sweep(states, [[1]])

        assert queued == 0
        users_crud.record_deletion_attempt.assert_not_called()
        publishers.publish_deletion_requested.assert_not_called()

    def test_an_account_no_longer_queued_for_deletion_is_not_queued(self, states):
        queued, _, publishers, _ = self._sweep(states, [[1]], attempts=None)

        assert queued == 0
        publishers.publish_deletion_requested.assert_not_called()
        assert states.begin(1, _Kind) is True

    def test_one_failure_does_not_stop_the_rest(self, states):
        queued, _, publishers, _ = self._sweep(states, [[1, 2]], publish_error=[RuntimeError("boom"), None])

        assert queued == 1
        assert publishers.publish_deletion_requested.call_count == 2
        assert states.get(1, _Kind).status == _Status.FAILED

    def test_the_last_automatic_attempt_is_logged_as_an_error(self, states, caplog):
        with caplog.at_level("ERROR"):
            self._sweep(states, [[1]], attempts=users_constants.DELETION_SWEEP_MAX_ATTEMPTS)

        assert "last automatic attempt" in caplog.text

    def test_a_full_pool_stops_the_pass_before_an_attempt_is_spent(self, states):
        clock = MagicMock()
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_MODULE}.core_database.SessionLocal"),
            patch(f"{_MODULE}.users_crud") as users_crud,
            patch(f"{_MODULE}._deletion_pool") as pool,
        ):
            users_crud.list_stalled_deletion_ids.side_effect = [[1, 2], []]
            pool.require_capacity.side_effect = core_local_pool.PoolFullError("full")

            queued = job_service.requeue_stalled_deletions(states, MagicMock(), clock)

        assert queued == 0
        users_crud.record_deletion_attempt.assert_not_called()
        assert states.get(1, _Kind) is None
