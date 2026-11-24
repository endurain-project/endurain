"""The shared Garmin Connect state (link attempts, MFA codes, syncs, rate limits) over the platform state."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.sync_state_store as sync_state_store
from tests._helpers.clock import platform_clock
from tests.garmin.conftest import UnavailableState

USER = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)
Status = core_job_status.JobState
Failure = garmin_constants.LinkFailure
Kind = garmin_constants.SyncKind


@pytest.fixture
def state() -> MemoryState:
    """The platform's state provider."""
    return jasil_runtime.get_state()


@pytest.fixture
def advance():
    """Return a function that moves the platform clock the state provider expires keys by."""
    return platform_clock().advance


class TestLinkState:
    def test_a_first_attempt_starts_running(self, state):
        store = link_state_store.GarminLinkStateStore(state)

        store.begin(USER, conflict="busy")

        assert store.get(USER) == link_state_store.LinkState(status=Status.RUNNING)

    def test_an_attempt_in_progress_blocks_another(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        store.begin(USER, conflict="busy")

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, conflict="busy")

    def test_an_attempt_waiting_for_mfa_still_blocks_another(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        job = store.begin(USER, conflict="busy")
        store.set_status(USER, job.id, Status.RUNNING, mfa_required=True)

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, conflict="busy")

    @pytest.mark.parametrize("outcome", [(Status.FAILED, Failure.INVALID_CREDENTIALS), (Status.SUCCEEDED, None)])
    def test_a_finished_attempt_can_be_repeated(self, state, outcome):
        store = link_state_store.GarminLinkStateStore(state)
        job = store.begin(USER, conflict="busy")
        store.set_status(USER, job.id, *outcome)

        store.begin(USER, conflict="busy")

        assert store.get(USER) == link_state_store.LinkState(status=Status.RUNNING)

    def test_the_claim_holds_even_when_the_state_entry_is_gone(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        store.begin(USER, conflict="busy")
        state.delete(core_attempt_state.key("garmin", "link:state", str(USER)))

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, conflict="busy")

    def test_users_do_not_block_each_other(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        store.begin(USER, conflict="busy")

        store.begin(OTHER, conflict="busy")

    def test_no_attempt_reads_as_none(self, state):
        assert link_state_store.GarminLinkStateStore(state).get(uuid.UUID(int=99)) is None

    def test_a_failure_carries_its_error_code(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        job = store.begin(USER, conflict="busy")

        store.set_status(USER, job.id, Status.FAILED, Failure.INCORRECT_MFA)

        assert store.get(USER) == link_state_store.LinkState(status=Status.FAILED, error_code=Failure.INCORRECT_MFA)

    def test_an_attempt_a_newer_one_superseded_records_nothing(self, state):
        store = link_state_store.GarminLinkStateStore(state)
        old = store.begin(USER, conflict="busy")
        store.release(USER)
        store.begin(USER, conflict="busy")

        store.set_status(USER, old.id, Status.FAILED, Failure.INTERNAL)

        assert store.get(USER) == link_state_store.LinkState(status=Status.RUNNING)

    def test_an_unavailable_backend_does_not_fail_a_recorded_outcome(self):
        link_state_store.GarminLinkStateStore(UnavailableState()).set_status(USER, uuid.uuid4(), Status.SUCCEEDED)

    def test_an_unavailable_backend_refuses_a_new_attempt(self):
        with pytest.raises(core_attempt_state.StateUnavailableError):
            link_state_store.GarminLinkStateStore(UnavailableState()).begin(USER, conflict="busy")

    def test_a_claim_is_not_left_behind_when_the_pending_state_cannot_be_written(self):
        class StateWriteFails(MemoryState):
            writes_fail = True

            def set(self, key, value, ttl_seconds=None):
                if self.writes_fail:
                    raise StateBackendUnavailableError("down")
                super().set(key, value, ttl_seconds)

        failing = StateWriteFails(platform_clock())
        with pytest.raises(core_attempt_state.StateUnavailableError):
            link_state_store.GarminLinkStateStore(failing).begin(USER, conflict="busy")

        failing.writes_fail = False
        link_state_store.GarminLinkStateStore(failing).begin(USER, conflict="busy")

    def test_progress_renews_the_claim(self, state, advance):
        store = link_state_store.GarminLinkStateStore(state, ttl_seconds=60)
        job = store.begin(USER, conflict="busy")
        advance(40)
        store.set_status(USER, job.id, Status.RUNNING, mfa_required=True)
        advance(40)

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, conflict="busy")

    def test_a_silent_attempt_releases_its_claim_when_the_lifetime_ends(self, state, advance):
        store = link_state_store.GarminLinkStateStore(state, ttl_seconds=60)
        store.begin(USER, conflict="busy")
        advance(61)

        store.begin(USER, conflict="busy")


class TestMfaCodeStore:
    def test_a_code_is_stored_and_read_back(self, state):
        store = mfa_code_store.GarminMFACodeStore(state)

        store.add_code(USER, "123456")

        assert store.get_code(USER) == "123456"

    def test_a_missing_code_reads_as_none(self, state):
        assert mfa_code_store.GarminMFACodeStore(state).get_code(uuid.UUID(int=99)) is None

    def test_a_deleted_code_is_gone_and_deleting_a_missing_one_is_a_no_op(self, state):
        store = mfa_code_store.GarminMFACodeStore(state)
        store.add_code(USER, "abc")

        store.delete_code(USER)
        store.delete_code(USER)

        assert store.get_code(USER) is None

    def test_a_newer_code_replaces_the_older(self, state):
        store = mfa_code_store.GarminMFACodeStore(state)
        store.add_code(USER, "old")
        store.add_code(USER, "new")

        assert store.get_code(USER) == "new"

    def test_users_codes_are_isolated(self, state):
        store = mfa_code_store.GarminMFACodeStore(state)
        store.add_code(USER, "aaa")
        store.add_code(OTHER, "bbb")

        assert (store.get_code(USER), store.get_code(OTHER)) == ("aaa", "bbb")

    def test_the_code_is_not_stored_in_plaintext(self, state):
        mfa_code_store.GarminMFACodeStore(state).add_code(USER, "123456")

        stored = state.get(core_attempt_state.key("garmin", "mfa:code", str(USER)))

        assert stored is not None
        assert b"123456" not in stored

    def test_a_code_expires(self, state, advance):
        store = mfa_code_store.GarminMFACodeStore(state, ttl_seconds=30)
        store.add_code(USER, "123456")
        advance(31)

        assert store.get_code(USER) is None

    def test_an_unavailable_backend_fails_a_write_and_a_read(self):
        store = mfa_code_store.GarminMFACodeStore(UnavailableState())

        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.add_code(USER, "x")
        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.get_code(USER)

    def test_an_unavailable_backend_does_not_fail_a_delete(self):
        """Delete is best-effort: the entry expires on its own."""
        mfa_code_store.GarminMFACodeStore(UnavailableState()).delete_code(USER)


class TestSyncState:
    def test_a_first_sync_is_queued_and_blocks_another_of_its_kind(self, state):
        store = sync_state_store.GarminSyncStateStore(state)

        store.begin(USER, Kind.GEAR, conflict="busy")

        assert store.get(USER, Kind.GEAR) == core_attempt_state.SyncState(status=Status.QUEUED)
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, Kind.GEAR, conflict="busy")

    def test_progress_keeps_blocking_until_the_sync_finishes(self, state):
        store = sync_state_store.GarminSyncStateStore(state)
        job = store.begin(USER, Kind.HEALTH, conflict="busy")
        store.set_status(USER, Kind.HEALTH, Status.RUNNING, job_id=job.id)
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            store.begin(USER, Kind.HEALTH, conflict="busy")

        store.set_status(USER, Kind.HEALTH, Status.SUCCEEDED, job_id=job.id)

        assert store.get(USER, Kind.HEALTH).status == Status.SUCCEEDED
        store.begin(USER, Kind.HEALTH, conflict="busy")

    def test_a_failed_sync_can_be_retried(self, state):
        store = sync_state_store.GarminSyncStateStore(state)
        job = store.begin(USER, Kind.GEAR, conflict="busy")
        store.set_status(USER, Kind.GEAR, Status.FAILED, job_id=job.id)

        store.begin(USER, Kind.GEAR, conflict="busy")

    def test_kinds_and_users_do_not_block_each_other(self, state):
        store = sync_state_store.GarminSyncStateStore(state)
        store.begin(USER, Kind.GEAR, conflict="busy")

        store.begin(USER, Kind.HEALTH, conflict="busy")
        store.begin(OTHER, Kind.GEAR, conflict="busy")

    def test_no_sync_reads_as_none(self, state):
        assert sync_state_store.GarminSyncStateStore(state).get(uuid.UUID(int=99), Kind.GEAR) is None

    def test_an_unavailable_backend_fails_a_read_and_a_begin_but_not_a_recorded_outcome(self):
        store = sync_state_store.GarminSyncStateStore(UnavailableState())

        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.begin(USER, Kind.GEAR, conflict="busy")
        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.get(USER, Kind.GEAR)
        store.set_status(USER, Kind.GEAR, Status.SUCCEEDED, job_id=uuid.uuid4())


class TestRateLimitState:
    def test_nothing_is_limited_to_begin_with(self, state):
        assert garmin_rate_limit_store.GarminRateLimitStore(state).rate_limited_until(USER) is None

    def test_a_limit_lasts_one_cooldown_and_is_visible_to_another_replica(self, state):
        before = datetime.now(UTC)

        until = garmin_rate_limit_store.GarminRateLimitStore(state).mark_rate_limited(USER)

        assert before + timedelta(seconds=garmin_constants.RATE_LIMIT_COOLDOWN_SECONDS) <= until
        assert garmin_rate_limit_store.GarminRateLimitStore(state).rate_limited_until(USER) == until

    def test_the_limit_is_per_user(self, state):
        store = garmin_rate_limit_store.GarminRateLimitStore(state)
        store.mark_rate_limited(USER)

        assert store.rate_limited_until(OTHER) is None

    def test_an_unreachable_state_reads_as_not_limited(self):
        assert garmin_rate_limit_store.GarminRateLimitStore(UnavailableState()).rate_limited_until(USER) is None

    def test_only_one_caller_holds_the_token_refresh_claim_until_it_is_released(self, state):
        store = garmin_rate_limit_store.GarminRateLimitStore(state)

        assert store.claim_token_refresh(USER)
        assert not store.claim_token_refresh(USER)
        assert store.claim_token_refresh(OTHER)

        store.release_token_refresh(USER)
        assert store.claim_token_refresh(USER)

    def test_an_abandoned_token_refresh_claim_expires(self, state, advance):
        store = garmin_rate_limit_store.GarminRateLimitStore(state)
        assert store.claim_token_refresh(USER)
        advance(garmin_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS + 1)

        assert store.claim_token_refresh(USER)
