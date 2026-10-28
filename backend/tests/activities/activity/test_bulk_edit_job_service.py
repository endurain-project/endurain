"""Tests for activity.bulk_edit_job_service: accepting, running and closing a bulk visibility edit."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_job_service as job_service
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity.events as activity_events

_MODULE = "modules.activities.activity.bulk_edit_job_service"
_Status = bulk_edit_constants.BulkEditStatus
_Kind = bulk_edit_constants.BulkEditKind.VISIBILITY


@pytest.fixture
def states():
    return bulk_edit_state_store.ActivityBulkEditStateStore(MemoryState())


@pytest.fixture
def mock_db():
    return MagicMock()


def _payload(user_id: int = 1, visibility: int = 2) -> activity_events.VisibilityEditRequestedPayload:
    return activity_events.VisibilityEditRequestedPayload(user_id=user_id, visibility=visibility)


class TestRequestVisibilityEdit:
    def _request(self, states, db, *, jobs_enabled):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=jobs_enabled)),
            patch(f"{_MODULE}.activity_event_publishers") as publishers,
            patch(f"{_MODULE}._pool") as pool,
        ):
            result = job_service.request_visibility_edit(1, 2, states, db)
        return result, publishers, pool

    def test_a_durable_request_publishes_the_work_and_answers_queued(self, states, mock_db):
        result, publishers, pool = self._request(states, mock_db, jobs_enabled=True)

        assert result.status == _Status.QUEUED
        publishers.publish_visibility_edit_requested.assert_called_once_with(1, 2, mock_db, commit=mock_db.commit)
        pool.submit.assert_not_called()
        assert states.get(1, _Kind).status == _Status.QUEUED

    def test_without_durable_jobs_the_work_runs_on_the_pool(self, states, mock_db):
        _, publishers, pool = self._request(states, mock_db, jobs_enabled=False)

        pool.require_capacity.assert_called_once_with()
        pool.submit.assert_called_once()
        publishers.publish_visibility_edit_requested.assert_not_called()

    def test_a_pending_edit_is_refused(self, states, mock_db):
        states.begin(1, _Kind)

        with pytest.raises(core_exceptions.ConflictError):
            self._request(states, mock_db, jobs_enabled=True)

    def test_a_failure_before_the_job_starts_frees_the_claim(self, states, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=True)),
            patch(f"{_MODULE}.activity_event_publishers") as publishers,
            pytest.raises(RuntimeError),
        ):
            publishers.publish_visibility_edit_requested.side_effect = RuntimeError("boom")
            job_service.request_visibility_edit(1, 2, states, mock_db)

        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True


class TestRunVisibilityEdit:
    def _run(self, states, *, batches, error=None, will_retry=False):
        crud = MagicMock()
        crud.edit_user_activities_visibility_batch.side_effect = error if error else [*batches, []]
        with (
            patch(f"{_MODULE}.core_database.SessionLocal") as session_local,
            patch(f"{_MODULE}.activity_crud", crud),
            patch(f"{_MODULE}.activity_event_publishers") as publishers,
        ):
            job_service.run_visibility_edit(_payload(), states, will_retry=will_retry)
        return crud, publishers, session_local

    def test_it_edits_batch_by_batch_until_nothing_is_left_to_change(self, states):
        states.begin(1, _Kind)

        crud, publishers, session_local = self._run(states, batches=[[1, 2], [3]])

        assert crud.edit_user_activities_visibility_batch.call_count == 3
        assert crud.edit_user_activities_visibility_batch.call_args.args[:3] == (
            1,
            2,
            bulk_edit_constants.BULK_EDIT_BATCH_SIZE,
        )
        assert [call.args[0] for call in publishers.publish_activities_updated.call_args_list] == [[1, 2], [3]]
        # Every batch commits in a transaction of its own.
        assert session_local.return_value.__enter__.return_value.commit.call_count == 3
        assert states.get(1, _Kind).status == _Status.COMPLETED

    def test_an_edit_that_is_not_pending_is_skipped(self, states):
        crud, _, _ = self._run(states, batches=[])

        crud.edit_user_activities_visibility_batch.assert_not_called()

    def test_a_failure_nothing_retries_fails_the_edit_and_frees_the_claim(self, states):
        states.begin(1, _Kind)

        self._run(states, batches=[], error=RuntimeError("boom"))

        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True

    def test_a_failure_a_worker_will_retry_stays_queued_and_raises(self, states):
        states.begin(1, _Kind)

        with pytest.raises(RuntimeError):
            self._run(states, batches=[], error=RuntimeError("boom"), will_retry=True)

        assert states.get(1, _Kind).status == _Status.QUEUED
        assert states.begin(1, _Kind) is False


class TestStatusAndDeadLetter:
    def test_status_is_not_found_when_none_is_recorded(self, states):
        with pytest.raises(core_exceptions.NotFoundError):
            job_service.get_visibility_edit_status(1, states)

    def test_status_reports_the_recorded_state(self, states):
        states.begin(1, _Kind)

        assert job_service.get_visibility_edit_status(1, states).status == _Status.QUEUED

    def test_a_dead_lettered_edit_is_failed_and_its_claim_freed(self, states):
        states.begin(1, _Kind)

        job_service.close_dead_lettered_visibility_edit(_payload(), states)

        assert states.get(1, _Kind).status == _Status.FAILED
        assert states.begin(1, _Kind) is True
