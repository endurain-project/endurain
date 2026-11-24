"""Linking a Garmin Connect account: the background login, the MFA hand-off, the stored token and its audit rows."""

import time
import uuid

import garminconnect
import pytest

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.sync_runner as core_sync_runner
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.integration_service as garmin_integration
import modules.garmin.link_service as garmin_link_service
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.schema as garmin_schema
from tests._factories.tokens import audit_rows
from tests.garmin.conftest import stored_access_token, stored_token

Status = core_job_status.JobState
Failure = garmin_constants.LinkFailure

_LOGIN = garmin_schema.GarminLogin(username="me@example.com", password="pw-secret")


def _link(user, mfa_codes, link_states, *, is_cn: bool = False) -> uuid.UUID:
    """Run a link attempt on this thread, as the login pool would, and return its job id."""
    job = link_states.begin(user.id, conflict="busy")
    garmin_link_service.link_garminconnect(user.id, job.id, "me@example.com", "pw", mfa_codes, link_states, is_cn)
    return job.id


def _job_hints(hints, kind: str = "garmin_link") -> list[dict]:
    return [hint for _, hint in hints if hint.get("kind") == kind]


class TestSuccessfulLink:
    def test_the_token_is_stored_encrypted_and_the_attempt_succeeds(
        self, committed_sessions, account, unlinked, mfa_codes, link_states
    ):
        _link(unlinked, mfa_codes, link_states)

        token = stored_token(committed_sessions, unlinked.id)
        assert token is not None
        assert token["di_token"] != "login-access"
        assert stored_access_token(committed_sessions, unlinked.id) == "login-access"
        assert link_states.get(unlinked.id) == garmin_link_state_store.LinkState(status=Status.SUCCEEDED)

    def test_the_china_region_is_asked_for_and_remembered(
        self, committed_sessions, account, unlinked, mfa_codes, link_states
    ):
        _link(unlinked, mfa_codes, link_states, is_cn=True)

        assert account.clients[0].is_cn is True
        assert stored_token(committed_sessions, unlinked.id)["is_cn"] is True

    def test_a_completed_link_is_audited_and_the_password_is_nowhere_in_it(
        self, committed_sessions, account, unlinked, mfa_codes, link_states
    ):
        _link(unlinked, mfa_codes, link_states)

        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
            "success",
            "user",
            str(unlinked.id),
            str(unlinked.id),
        )
        assert "pw" not in str(row.details)

    def test_a_completed_link_is_announced_once(self, account, unlinked, mfa_codes, link_states, hints):
        job_id = _link(unlinked, mfa_codes, link_states)

        finished = [hint for hint in _job_hints(hints) if hint["job_id"] == str(job_id)]
        assert len(finished) == 1


class TestRefusedLink:
    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (garminconnect.GarminConnectAuthenticationError("no"), Failure.INVALID_CREDENTIALS),
            (garminconnect.GarminConnectTooManyRequestsError("slow down"), Failure.TOO_MANY_REQUESTS),
        ],
    )
    def test_a_refusal_is_recorded_stores_nothing_and_is_audited_with_its_reason_only(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, error, reason
    ):
        def refuse(_garmin):
            raise error

        account.login_script = refuse

        _link(unlinked, mfa_codes, link_states)

        assert link_states.get(unlinked.id) == garmin_link_state_store.LinkState(
            status=Status.FAILED, error_code=reason
        )
        assert stored_token(committed_sessions, unlinked.id) is None
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert (row.outcome, row.target_owner_id, row.details) == (
            "failure",
            str(unlinked.id),
            {"reason": reason.value},
        )

    def test_a_login_that_returns_no_token_is_a_credentials_failure(
        self, committed_sessions, account, unlinked, mfa_codes, link_states
    ):
        account.login_script = lambda garmin: None

        _link(unlinked, mfa_codes, link_states)

        assert link_states.get(unlinked.id).error_code == Failure.INVALID_CREDENTIALS
        assert stored_token(committed_sessions, unlinked.id) is None
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert row.details == {"reason": "invalid_credentials"}

    @pytest.mark.parametrize(
        "error",
        [garminconnect.GarminConnectConnectionError("down"), RuntimeError("boom"), TypeError("not an mfa problem")],
    )
    def test_an_internal_error_is_recorded_without_an_audit_row(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, error
    ):
        def fail(_garmin):
            raise error

        account.login_script = fail

        _link(unlinked, mfa_codes, link_states)

        assert link_states.get(unlinked.id).error_code == Failure.INTERNAL
        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK) == []

    def test_a_failed_link_is_announced(self, account, unlinked, mfa_codes, link_states, hints):
        account.login_script = lambda garmin: (_ for _ in ()).throw(RuntimeError("boom"))

        job_id = _link(unlinked, mfa_codes, link_states)

        assert [hint for hint in _job_hints(hints) if hint["job_id"] == str(job_id)]


class TestMfaHandOff:
    def test_the_prompt_is_shared_state_and_the_submitted_code_reaches_the_login(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, monkeypatch
    ):
        seen_while_waiting: list[bool] = []
        received: list[str] = []

        def user_types_the_code(_seconds):
            seen_while_waiting.append(link_states.get(unlinked.id).mfa_required)
            garmin_link_service.submit_mfa_code(unlinked.id, "123456", mfa_codes, link_states)

        def login(garmin):
            received.append(garmin.prompt_mfa())
            garmin.client.di_token = "mfa-access"
            garmin.client.di_refresh_token = "mfa-refresh"

        account.login_script = login
        monkeypatch.setattr(time, "sleep", user_types_the_code)

        _link(unlinked, mfa_codes, link_states)

        assert received == ["123456"]
        assert seen_while_waiting == [True]
        assert link_states.get(unlinked.id) == garmin_link_state_store.LinkState(status=Status.SUCCEEDED)
        assert stored_access_token(committed_sessions, unlinked.id) == "mfa-access"
        assert mfa_codes.get_code(unlinked.id) is None

    def test_a_rejection_after_the_prompt_is_an_incorrect_code(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, monkeypatch
    ):
        def user_types_the_code(_seconds):
            garmin_link_service.submit_mfa_code(unlinked.id, "000000", mfa_codes, link_states)

        def login(garmin):
            garmin.prompt_mfa()
            raise garminconnect.GarminConnectAuthenticationError("MFA verification failed")

        account.login_script = login
        monkeypatch.setattr(time, "sleep", user_types_the_code)

        _link(unlinked, mfa_codes, link_states)

        assert link_states.get(unlinked.id).error_code == Failure.INCORRECT_MFA
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert row.details == {"reason": "incorrect_mfa"}

    def test_a_code_that_never_arrives_fails_without_reaching_garmin(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, monkeypatch, no_waiting
    ):
        monkeypatch.setattr(garmin_constants, "MFA_WAIT_SECONDS", 2)
        sent: list[str] = []
        account.login_script = lambda garmin: sent.append(garmin.prompt_mfa())

        _link(unlinked, mfa_codes, link_states)

        assert sent == []
        assert no_waiting == [1, 1]
        assert link_states.get(unlinked.id) == garmin_link_state_store.LinkState(
            status=Status.FAILED, error_code=Failure.INCORRECT_MFA
        )
        assert stored_token(committed_sessions, unlinked.id) is None
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert row.details == {"reason": "incorrect_mfa"}

    def test_an_mfa_timeout_is_an_incorrect_code_through_the_librarys_login_wrapping(
        self, committed_sessions, unlinked, mfa_codes, link_states, monkeypatch, no_waiting
    ):
        def client_login(_self, _email, _password, prompt_mfa=None, **_kwargs):
            prompt_mfa()

        # The real Garmin.login runs, so its final handler rewraps the timeout as a connection error.
        monkeypatch.setattr(garminconnect.client.Client, "login", client_login)
        monkeypatch.setattr(garmin_constants, "MFA_WAIT_SECONDS", 1)

        _link(unlinked, mfa_codes, link_states)

        assert link_states.get(unlinked.id) == garmin_link_state_store.LinkState(
            status=Status.FAILED, error_code=Failure.INCORRECT_MFA
        )
        [row] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_LINK)
        assert row.details == {"reason": "incorrect_mfa"}

    def test_a_stale_code_does_not_answer_the_prompt_and_is_cleared(self, account, unlinked, mfa_codes, link_states):
        mfa_codes.add_code(unlinked.id, "stale")
        seen: list[str | None] = []

        def login(garmin):
            seen.append(mfa_codes.get_code(unlinked.id))
            raise RuntimeError("boom")

        account.login_script = login

        _link(unlinked, mfa_codes, link_states)

        assert seen == [None]
        assert mfa_codes.get_code(unlinked.id) is None

    def test_asking_for_the_code_is_announced(self, account, unlinked, mfa_codes, link_states, hints, monkeypatch):
        monkeypatch.setattr(
            time, "sleep", lambda _s: garmin_link_service.submit_mfa_code(unlinked.id, "123456", mfa_codes, link_states)
        )
        account.login_script = lambda garmin: garmin.prompt_mfa()

        job_id = _link(unlinked, mfa_codes, link_states)

        assert len([hint for hint in _job_hints(hints) if hint["job_id"] == str(job_id)]) == 2


class TestSubmitMfaCode:
    def test_a_code_is_taken_while_the_login_waits_for_it(self, unlinked, mfa_codes, link_states):
        job = link_states.begin(unlinked.id, conflict="busy")
        link_states.set_status(unlinked.id, job.id, Status.RUNNING, mfa_required=True)

        garmin_link_service.submit_mfa_code(unlinked.id, "123456", mfa_codes, link_states)

        assert mfa_codes.get_code(unlinked.id) == "123456"

    def test_a_code_with_no_login_waiting_is_a_conflict(self, unlinked, mfa_codes, link_states):
        link_states.begin(unlinked.id, conflict="busy")

        with pytest.raises(core_exceptions.ConflictError):
            garmin_link_service.submit_mfa_code(unlinked.id, "123456", mfa_codes, link_states)

        assert mfa_codes.get_code(unlinked.id) is None


class TestStartLink:
    def test_the_login_runs_on_the_pool_and_the_outcome_is_recorded(
        self, committed_sessions, account, unlinked, mfa_codes, link_states, link_pool
    ):
        started = garmin_link_service.start_link(unlinked.id, _LOGIN, mfa_codes, link_states)
        link_pool.shutdown(wait=True)

        assert (started.kind, started.status) == ("garmin_link", Status.RUNNING)
        assert link_states.current_job(unlinked.id).id == started.id
        assert link_states.get(unlinked.id).status == Status.SUCCEEDED
        assert stored_access_token(committed_sessions, unlinked.id) == "login-access"
        assert (account.clients[0].email, account.clients[0].password) == ("me@example.com", "pw-secret")

    def test_a_link_beyond_the_capacity_is_refused_and_leaves_no_attempt_behind(
        self, committed_sessions, account, make_linked, mfa_codes, link_states, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(core_sync_runner.MAX_CONCURRENT_LINKS))
        account.login_script = lambda garmin: blocked_pool.release.wait(10)
        users = [make_linked() for _ in range(core_sync_runner.MAX_CONCURRENT_LINKS + 1)]
        for user in users[:-1]:
            garmin_link_service.start_link(user.id, _LOGIN, mfa_codes, link_states)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            garmin_link_service.start_link(users[-1].id, _LOGIN, mfa_codes, link_states)

        assert link_states.get(users[-1].id) is None

    def test_a_refused_duplicate_link_takes_no_capacity(
        self, account, make_linked, mfa_codes, link_states, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_link_service, "_link_pool", blocked_pool(2))
        account.login_script = lambda garmin: blocked_pool.release.wait(10)
        first, second = make_linked(), make_linked()
        garmin_link_service.start_link(first.id, _LOGIN, mfa_codes, link_states)
        for _ in range(3):
            with pytest.raises(core_exceptions.ConflictError):
                garmin_link_service.start_link(first.id, _LOGIN, mfa_codes, link_states)

        assert garmin_link_service.start_link(second.id, _LOGIN, mfa_codes, link_states).status == Status.RUNNING

    def test_a_link_that_cannot_start_releases_its_claim(
        self, unlinked, mfa_codes, link_states, closed_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_link_service, "_link_pool", closed_pool)
        with pytest.raises(RuntimeError):
            garmin_link_service.start_link(unlinked.id, _LOGIN, mfa_codes, link_states)

        link_states.begin(unlinked.id, conflict="busy")


class TestReadLinkJob:
    def test_a_job_reads_with_its_id_kind_and_progress(self, unlinked, link_states):
        import jasil.runtime as jasil_runtime

        job = link_states.begin(unlinked.id, conflict="busy")
        link_states.set_status(unlinked.id, job.id, Status.RUNNING, mfa_required=True)

        read = garmin_integration.read_link_job(job, jasil_runtime.get_state())

        assert (read.id, read.kind, read.status, read.mfa_required) == (job.id, "garmin_link", Status.RUNNING, True)

    def test_an_earlier_job_reads_as_gone_once_the_user_links_again(self, unlinked, link_states):
        import jasil.runtime as jasil_runtime

        first = link_states.begin(unlinked.id, conflict="busy")
        link_states.set_status(unlinked.id, first.id, Status.FAILED, Failure.INVALID_CREDENTIALS)
        second = link_states.begin(unlinked.id, conflict="busy")
        state = jasil_runtime.get_state()

        assert garmin_integration.read_link_job(first, state) is None
        assert garmin_integration.read_link_job(second, state).id == second.id

    def test_an_expired_job_reads_as_gone(self, unlinked, link_states):
        import jasil.runtime as jasil_runtime

        state = jasil_runtime.get_state()
        job = link_states.begin(unlinked.id, conflict="busy")
        link_states.release(unlinked.id)
        state.delete(core_attempt_state.key("garmin", "link:state", str(unlinked.id)))

        assert garmin_integration.read_link_job(job, state) is None
