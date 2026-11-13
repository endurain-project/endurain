"""Tests for core.attempt_state (provider-backed claim, polled state and the job index)."""

import uuid
from enum import StrEnum
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from pydantic import BaseModel

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID


class _State(BaseModel):
    step: str


def _store(state=None, ttl=60, announce=None) -> core_attempt_state.AttemptStateStore:
    return core_attempt_state.AttemptStateStore(state or MemoryState(), "feature", "job", ttl, announce=announce)


def _begin(store, subject="1", owner_id=MOCK_USER_ID):
    return store.begin(subject, _State(step="queued"), kind="feature_job", owner_id=owner_id, conflict="Busy")


def test_keys_are_namespaced_by_feature_and_kind():
    state = MemoryState()
    store = _store(state)
    _begin(store)

    assert state.get(core_attempt_state.key("feature", "job:state", "1")) is not None
    assert state.get(core_attempt_state.key("feature", "job:claim", "1")) is not None
    assert core_attempt_state.key("garmin", "link:state", "1") == "endurain:garmin:link:state:1"


def test_begin_starts_a_job_with_its_own_id_and_indexes_it():
    state = MemoryState()
    store = _store(state)

    job = _begin(store, owner_id=OTHER_USER_ID)

    assert job.kind == "feature_job"
    assert job.owner_id == OTHER_USER_ID
    assert job.subject == "1"
    assert job.finished_at is None
    assert core_attempt_state.JobIndex(state).get(job.id) == job
    assert core_attempt_state.JobIndex(state).list_owned(OTHER_USER_ID) == [job]
    assert core_attempt_state.JobIndex(state).list_owned(uuid.uuid4()) == []


def test_a_second_begin_is_refused_with_the_running_job_until_the_attempt_finishes():
    store = _store()
    first = _begin(store)

    with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
        _begin(store)

    assert refused.value.detail == "Busy"
    assert refused.value.job_id == first.id
    store.record("1", _State(step="done"), finished=True)
    assert _begin(store).id != first.id


def test_a_claim_whose_job_expired_is_refused_without_naming_a_job():
    state = MemoryState()
    store = _store(state)
    state.set(core_attempt_state.key("feature", "job:claim", "1"), str(uuid.uuid4()).encode(), ttl_seconds=60)

    with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
        _begin(store)

    assert refused.value.job_id is None


def test_job_ids_are_uuids():
    job = _begin(_store())

    assert isinstance(job.id, uuid.UUID)


def test_subjects_and_features_do_not_block_each_other():
    state = MemoryState()
    store = _store(state)
    other_feature = core_attempt_state.AttemptStateStore(state, "other", "job", 60)
    _begin(store)

    _begin(store, subject="2")
    _begin(other_feature)


def test_read_returns_the_recorded_state_or_none():
    store = _store()
    assert store.read("1") is None

    _begin(store)
    store.record("1", _State(step="running"), finished=False)

    assert _State.model_validate_json(store.read("1")) == _State(step="running")


def test_a_finished_record_stamps_the_job_and_announces_it():
    state = MemoryState()
    announce = MagicMock()
    store = _store(state, announce=announce)
    job = _begin(store)

    store.record("1", _State(step="running"), finished=False)
    announce.assert_not_called()
    store.record("1", _State(step="done"), finished=True)

    finished = core_attempt_state.JobIndex(state).get(job.id)
    assert finished is not None
    assert finished.finished_at is not None
    announce.assert_called_once_with(finished)


def test_read_job_returns_the_job_only_while_its_subject_still_holds_it():
    store = _store()
    first = _begin(store)
    store.record("1", _State(step="done"), finished=True)

    stored = store.read_job(first)
    assert stored is not None
    assert stored.job.id == first.id
    assert _State.model_validate_json(stored.state_json()) == _State(step="done")

    second = _begin(store)

    assert store.read_job(first) is None
    assert store.read_job(second).job.id == second.id


def test_a_record_without_a_job_keeps_no_state_but_still_frees_the_claim():
    state = MemoryState()
    store = _store(state)
    state.set(core_attempt_state.key("feature", "job:claim", "1"), b"1", ttl_seconds=60)
    state.set(core_attempt_state.key("feature", "job:state", "1"), b'{"step":"queued"}', ttl_seconds=60)

    assert store.read("1") is None
    store.record("1", _State(step="done"), finished=True)

    assert store.read("1") is None
    _begin(store)


def test_progress_renews_the_claim():
    state = MemoryState()
    store = _store(state)
    _begin(store)
    with patch.object(state, "set") as write:
        store.record("1", _State(step="running"), finished=False)

    assert core_attempt_state.key("feature", "job:claim", "1") in [call.args[0] for call in write.call_args_list]


def test_release_frees_the_claim_without_touching_the_state():
    store = _store()
    _begin(store)

    store.release("1")

    assert store.read("1") is not None
    _begin(store)


def test_discard_removes_the_claim_the_state_and_the_job():
    state = MemoryState()
    store = _store(state)
    job = _begin(store)

    store.discard("1")

    assert store.read("1") is None
    assert core_attempt_state.JobIndex(state).get(job.id) is None
    assert core_attempt_state.JobIndex(state).list_owned(MOCK_USER_ID) == []
    _begin(store)


def test_an_outage_while_discarding_is_swallowed():
    state = MemoryState()
    store = _store(state)
    _begin(store)
    with patch.object(state, "delete", side_effect=StateBackendUnavailableError("down")):
        store.discard("1")


def test_a_claim_is_not_left_behind_when_the_first_state_cannot_be_written():
    state = MemoryState()
    store = _store(state)
    with (
        patch.object(state, "set", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        _begin(store)

    _begin(store)


def test_an_outage_on_read_is_a_service_unavailable_error():
    state = MemoryState()
    store = _store(state)
    with (
        patch.object(state, "get", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        store.read("1")


def test_an_outage_while_recording_or_releasing_is_swallowed():
    state = MemoryState()
    store = _store(state)
    _begin(store)
    with patch.object(state, "set", side_effect=StateBackendUnavailableError("down")):
        store.record("1", _State(step="running"), finished=False)
    with patch.object(state, "delete", side_effect=StateBackendUnavailableError("down")):
        store.release("1")


def test_an_outage_while_recording_strictly_raises():
    state = MemoryState()
    store = _store(state)
    _begin(store)
    with (
        patch.object(state, "set", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        store.record("1", _State(step="running"), finished=False, strict=True)


def test_an_outage_reading_the_index_is_a_service_unavailable_error():
    state = MagicMock()
    state.get.side_effect = StateBackendUnavailableError("down")
    state.iter_keys.side_effect = StateBackendUnavailableError("down")
    index = core_attempt_state.JobIndex(state)

    with pytest.raises(core_attempt_state.StateUnavailableError):
        index.get(uuid.uuid4())
    with pytest.raises(core_attempt_state.StateUnavailableError):
        index.list_owned(MOCK_USER_ID)


class _Kind(StrEnum):
    GEAR = "gear"
    HEALTH = "health"


Status = core_job_status.JobState


def _syncs(state=None, announce=None) -> core_attempt_state.SyncStateStore:
    return core_attempt_state.SyncStateStore(
        state or MemoryState(), "feature", 60, job_kind=lambda kind: f"feature_{kind.value}", announce=announce
    )


def _queue(syncs, user_id, kind, owner_id=None):
    return syncs.begin(user_id, kind, conflict="Busy", owner_id=owner_id)


class TestSyncStateStore:
    def test_a_first_sync_is_queued_as_a_job_of_its_kind_and_blocks_another(self):
        syncs = _syncs()

        job = _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

        assert job.kind == "feature_gear"
        assert job.owner_id == MOCK_USER_ID
        assert syncs.get(MOCK_USER_ID, _Kind.GEAR) == core_attempt_state.SyncState(status=Status.QUEUED)
        with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        assert refused.value.job_id == job.id

    def test_another_user_can_own_the_sync(self):
        assert _queue(_syncs(), OTHER_USER_ID, _Kind.GEAR, owner_id=MOCK_USER_ID).owner_id == MOCK_USER_ID

    def test_progress_keeps_blocking_until_the_sync_finishes(self):
        announce = MagicMock()
        syncs = _syncs(announce=announce)
        job = _queue(syncs, MOCK_USER_ID, _Kind.HEALTH)
        syncs.set_status(MOCK_USER_ID, _Kind.HEALTH, Status.RUNNING)
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            _queue(syncs, MOCK_USER_ID, _Kind.HEALTH)

        syncs.set_status(MOCK_USER_ID, _Kind.HEALTH, Status.SUCCEEDED)

        assert syncs.get(MOCK_USER_ID, _Kind.HEALTH).status == Status.SUCCEEDED
        assert announce.call_args.args[0].id == job.id
        _queue(syncs, MOCK_USER_ID, _Kind.HEALTH)

    def test_a_failed_sync_can_be_retried(self):
        syncs = _syncs()
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        syncs.set_status(MOCK_USER_ID, _Kind.GEAR, Status.FAILED)

        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

    def test_read_job_returns_the_sync_while_it_is_the_latest_of_its_kind(self):
        syncs = _syncs()
        first = _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        syncs.set_status(MOCK_USER_ID, _Kind.GEAR, Status.SUCCEEDED)

        job, state = syncs.read_job(first)
        assert job.id == first.id
        assert job.finished_at is not None
        assert state.status == Status.SUCCEEDED

        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        assert syncs.read_job(first) is None

    def test_a_discarded_sync_leaves_no_state_and_frees_the_claim(self):
        syncs = _syncs()
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

        syncs.discard(MOCK_USER_ID, _Kind.GEAR)

        assert syncs.get(MOCK_USER_ID, _Kind.GEAR) is None
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

    def test_kinds_users_and_features_do_not_block_each_other(self):
        state = MemoryState()
        syncs = _syncs(state)
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

        _queue(syncs, MOCK_USER_ID, _Kind.HEALTH)
        _queue(syncs, OTHER_USER_ID, _Kind.GEAR)
        other = core_attempt_state.SyncStateStore(state, "other", 60, job_kind=lambda kind: kind.value)
        _queue(other, MOCK_USER_ID, _Kind.GEAR)

    def test_the_keys_are_the_ones_each_feature_always_used(self):
        state = MemoryState()
        _queue(_syncs(state), MOCK_USER_ID, _Kind.GEAR)

        assert state.get(f"endurain:feature:sync:state:{MOCK_USER_ID}:gear") is not None
        assert state.get(f"endurain:feature:sync:claim:{MOCK_USER_ID}:gear") is not None

    def test_no_sync_reads_as_none(self):
        assert _syncs().get(uuid.uuid4(), _Kind.GEAR) is None

    @pytest.mark.parametrize("pending", [Status.QUEUED, Status.RUNNING])
    def test_a_pending_sync_is_closed_as_failed_and_frees_the_claim(self, pending):
        syncs = _syncs()
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        syncs.set_status(MOCK_USER_ID, _Kind.GEAR, pending)

        assert syncs.close_pending(MOCK_USER_ID, _Kind.GEAR) is True
        assert syncs.get(MOCK_USER_ID, _Kind.GEAR).status == Status.FAILED
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)

    @pytest.mark.parametrize("finished", [Status.SUCCEEDED, Status.FAILED])
    def test_a_finished_sync_is_left_as_it_is(self, finished):
        syncs = _syncs()
        _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        syncs.set_status(MOCK_USER_ID, _Kind.GEAR, finished)

        assert syncs.close_pending(MOCK_USER_ID, _Kind.GEAR) is False
        assert syncs.get(MOCK_USER_ID, _Kind.GEAR).status == finished

    def test_an_expired_sync_is_left_alone(self):
        assert _syncs().close_pending(MOCK_USER_ID, _Kind.GEAR) is False

    def test_an_unavailable_backend_fails_a_read_and_a_begin_but_not_a_recorded_outcome(self):
        state = MagicMock()
        for method in ("set", "get", "delete", "set_if_absent"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        syncs = _syncs(state)

        with pytest.raises(core_attempt_state.StateUnavailableError):
            _queue(syncs, MOCK_USER_ID, _Kind.GEAR)
        with pytest.raises(core_attempt_state.StateUnavailableError):
            syncs.get(MOCK_USER_ID, _Kind.GEAR)
        syncs.set_status(MOCK_USER_ID, _Kind.GEAR, Status.SUCCEEDED)


def test_a_sync_state_stored_before_the_job_vocabulary_reads_as_the_new_one():
    old = core_attempt_state.SyncState.model_validate_json(b'{"status":"completed"}')

    assert old.status == core_job_status.JobState.SUCCEEDED
