"""Tests for the identity-provider step-up of accounts without a local password."""

import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.schema as idp_schema
from modules.auth.identity_providers.constants import StepUpAction
from modules.auth.identity_providers.step_up_ticket_store import StepUpTicketStore

USER_ID = 7
SESSION_ID = "11111111-2222-3333-4444-555555555555"
VERIFIER = "v" * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def store(state):
    return step_up_store_module.StepUpAttempts(state)


@pytest.fixture
def account():
    """A password-less account; MFA off unless a test turns it on."""
    with (
        patch.object(step_up_service.users_integration, "require_user"),
        patch.object(step_up_service.credentials_integration, "get_password_hash", return_value=None),
        patch.object(step_up_service.mfa_integration, "is_mfa_enabled_for_user", return_value=False) as mfa_enabled,
        patch.object(step_up_service.mfa_integration, "verify_user_mfa", return_value=True) as verify_mfa,
    ):
        yield MagicMock(mfa_enabled=mfa_enabled, verify_mfa=verify_mfa)


def _issue(state, **overrides) -> str:
    fields = {
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "idp_id": 3,
        "code_challenge": CHALLENGE,
        "action": StepUpAction.API_KEY_CREATE,
    } | overrides
    return StepUpTicketStore(state).issue(idp_contracts.StepUpTicket(**fields))


def _verify(store, ticket: str | None, *, verifier: str = VERIFIER, mfa_code: str | None = None, **overrides):
    proof = idp_schema.IdpReauthProof(ticket=ticket, code_verifier=verifier) if ticket else None
    step_up_service.verify_step_up_credentials(
        USER_ID,
        None,
        mfa_code,
        store,
        MagicMock(),
        idp_reauth=proof,
        session_id=overrides.get("session_id", SESSION_ID),
        action=overrides.get("action", StepUpAction.API_KEY_CREATE),
    )


def _failures(store) -> int:
    """Return the failures recorded so far (recording one more to read the count)."""
    return store.record_failed_attempt(f"user:{USER_ID}") - 1


class TestChallenge:
    def test_a_request_without_proof_is_challenged_for_a_fresh_sign_in(self, store, account):
        with pytest.raises(core_exceptions.IdpReauthRequiredError) as exc_info:
            _verify(store, None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "idp-reauth-required"
        assert exc_info.value.headers == {
            "WWW-Authenticate": 'Bearer error="insufficient_user_authentication", max_age="60"'
        }

    def test_the_challenge_is_not_counted_as_a_failure(self, store, account):
        with pytest.raises(core_exceptions.IdpReauthRequiredError):
            _verify(store, None)

        assert _failures(store) == 0

    def test_mfa_alone_no_longer_passes(self, store, account):
        account.mfa_enabled.return_value = True

        with pytest.raises(core_exceptions.IdpReauthRequiredError):
            _verify(store, None, mfa_code="123456")


class TestTicket:
    def test_a_matching_ticket_passes_and_is_redeemed(self, state, store, account):
        ticket = _issue(state)

        _verify(store, ticket)

        assert StepUpTicketStore(state).read(ticket) is None

    @pytest.mark.parametrize(
        ("issued", "presented"),
        [
            ({"user_id": USER_ID + 1}, {}),
            ({"session_id": "99999999-2222-3333-4444-555555555555"}, {}),
            ({"action": StepUpAction.ACCOUNT_DELETE}, {}),
            ({}, {"verifier": "w" * 43}),
        ],
        ids=["another-user", "another-session", "another-action", "wrong-verifier"],
    )
    def test_a_ticket_issued_for_something_else_is_refused_and_counted(self, state, store, account, issued, presented):
        ticket = _issue(state, **issued)

        with pytest.raises(core_exceptions.UnauthenticatedError) as exc_info:
            _verify(store, ticket, **presented)

        assert not isinstance(exc_info.value, core_exceptions.IdpReauthRequiredError)
        assert _failures(store) == 1
        # Refused before redemption: the ticket is still there for its rightful request.
        assert StepUpTicketStore(state).read(ticket) is not None

    def test_an_unknown_ticket_is_refused(self, store, account):
        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(store, "u" * 43)

    def test_a_ticket_pays_for_one_request(self, state, store, account):
        ticket = _issue(state)
        _verify(store, ticket)

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(store, ticket)

    def test_without_a_session_or_action_no_ticket_matches(self, state, store, account):
        ticket = _issue(state)

        with pytest.raises(core_exceptions.UnauthenticatedError):
            step_up_service.verify_step_up_credentials(
                USER_ID,
                None,
                None,
                store,
                MagicMock(),
                idp_reauth=idp_schema.IdpReauthProof(ticket=ticket, code_verifier=VERIFIER),
            )

    def test_a_ticket_redeemed_by_a_racing_request_is_refused(self, state, store, account):
        ticket = _issue(state)
        racing = MagicMock(wraps=store)
        racing.is_locked_out.return_value = False
        racing.read_ticket.side_effect = store.read_ticket
        racing.redeem_ticket.return_value = None

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(racing, ticket)


class TestTicketWithMfa:
    def test_the_ticket_and_the_code_both_pass(self, state, store, account):
        account.mfa_enabled.return_value = True
        ticket = _issue(state)

        _verify(store, ticket, mfa_code="123456")

        assert StepUpTicketStore(state).read(ticket) is None

    def test_a_missing_code_is_refused_and_keeps_the_ticket(self, state, store, account):
        account.mfa_enabled.return_value = True
        ticket = _issue(state)

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(store, ticket)

        assert StepUpTicketStore(state).read(ticket) is not None

    def test_a_wrong_code_is_refused_and_keeps_the_ticket_for_a_retry(self, state, store, account):
        account.mfa_enabled.return_value = True
        account.verify_mfa.return_value = False
        ticket = _issue(state)

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _verify(store, ticket, mfa_code="000000")

        account.verify_mfa.return_value = True
        _verify(store, ticket, mfa_code="123456")


class TestAccountsWithAPassword:
    def test_a_password_account_still_needs_its_password_even_with_a_ticket(self, state, store, account):
        ticket = _issue(state)

        with (
            patch.object(step_up_service.credentials_integration, "get_password_hash", return_value="hash"),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _verify(store, ticket)


class TestRequireNotLockedOut:
    def test_a_locked_out_user_cannot_start_a_step_up(self, store):
        for _ in range(5):
            store.record_failed_attempt(f"user:{USER_ID}")

        with pytest.raises(core_exceptions.TooManyRequestsError):
            step_up_service.require_not_locked_out(USER_ID, store)

    def test_a_user_in_good_standing_can_start_one(self, store):
        step_up_service.require_not_locked_out(USER_ID, store)
