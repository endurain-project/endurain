"""What SSO keeps in the platform state: link tickets, step-up tickets, staged sign-ins, refresh claims and the logout
tokens already used.

The state is the platform's in-memory backend; an outage is a backend that is down.
"""

import logging
import uuid

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.logout_token_replay_store as logout_token_replay_store
import modules.auth.identity_providers.refresh_claim_store as refresh_claim_store
from modules.auth.identity_providers.link_ticket_store import LinkTicketStore
from modules.auth.identity_providers.staged_sign_in_store import StagedSignInStore
from modules.auth.identity_providers.step_up_ticket_store import StepUpTicketStore

USER_ID = uuid.UUID(int=7)
SESSION_ID = uuid.UUID(int=9)
IDP_ID = uuid.UUID(int=99)


class DownState(MemoryState):
    """A state backend that cannot be reached, as when the Redis behind it is down."""

    def get(self, key, *args, **kwargs):
        raise StateBackendUnavailableError("down")

    def set(self, key, value, *args, **kwargs):
        raise StateBackendUnavailableError("down")

    def delete(self, key):
        raise StateBackendUnavailableError("down")

    def set_if_absent(self, key, value, *args, **kwargs):
        raise StateBackendUnavailableError("down")

    def get_and_delete(self, key):
        raise StateBackendUnavailableError("down")


def _keys(state: MemoryState) -> list[str]:
    return list(state.iter_keys(""))


LINK = idp_contracts.LinkTicket(authorization_url="https://idp.example.com/authorize?state=s", browser_binding="b" * 43)
STEP_UP = idp_contracts.StepUpTicket(
    user_id=USER_ID, session_id=SESSION_ID, idp_id=IDP_ID, code_challenge="c" * 43, action="api_key_create"
)
STAGED = idp_contracts.StagedSignIn(
    user_id=USER_ID,
    idp_id=IDP_ID,
    subject="subject-secret-1",
    create_link=True,
    claims=idp_contracts.SyncedClaims(name="Alice Example", email="alice@example.com", email_verified=True),
)


class TestLinkTickets:
    def test_a_ticket_redeems_once_to_what_was_issued(self):
        store = LinkTicketStore(MemoryState())
        value = store.issue(LINK)

        assert store.redeem(value) == LINK
        assert store.redeem(value) is None

    def test_tickets_are_distinct_url_safe_and_unknown_ones_redeem_to_nothing(self):
        store = LinkTicketStore(MemoryState())

        first, second = store.issue(LINK), store.issue(LINK)

        assert first != second
        assert len(first) >= 43 and all(character.isalnum() or character in "-_" for character in first)
        assert store.redeem("unknown") is None

    def test_the_state_holds_the_digest_of_the_ticket_never_the_ticket(self):
        state = MemoryState()

        value = LinkTicketStore(state).issue(LINK)

        assert len(_keys(state)) == 1
        assert value not in _keys(state)[0]

    def test_a_malformed_stored_ticket_redeems_to_nothing(self):
        state = MemoryState()
        value = LinkTicketStore(state).issue(LINK)
        (key,) = _keys(state)
        state.set(key, b"not json", ttl_seconds=60)

        assert LinkTicketStore(state).redeem(value) is None

    def test_an_outage_fails_closed(self):
        store = LinkTicketStore(DownState())

        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.issue(LINK)
        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.redeem("t")


class TestStepUpTickets:
    def test_a_ticket_reads_back_what_was_issued_and_reading_does_not_redeem_it(self):
        store = StepUpTicketStore(MemoryState())
        value = store.issue(STEP_UP.model_copy(update={"security_generation": 5}))

        assert store.read(value).security_generation == 5
        assert store.redeem(value) is not None
        assert store.redeem(value) is None
        assert store.read(value) is None

    def test_a_ticket_without_a_stamp_reads_back_without_one(self):
        store = StepUpTicketStore(MemoryState())

        assert store.read(store.issue(STEP_UP)).security_generation is None

    def test_the_state_holds_only_the_digest_of_the_ticket(self):
        state = MemoryState()

        value = StepUpTicketStore(state).issue(STEP_UP)

        assert value not in _keys(state)[0]

    def test_an_unknown_or_malformed_ticket_reads_as_absent(self):
        state = MemoryState()
        store = StepUpTicketStore(state)
        value = store.issue(STEP_UP)
        state.set(_keys(state)[0], b"not json", ttl_seconds=60)

        assert store.read(value) is None
        assert store.read("unknown-ticket-value-that-was-never-issued-x") is None

    @pytest.mark.parametrize("operation", ["issue", "read", "redeem"])
    def test_an_outage_fails_closed(self, operation):
        store = StepUpTicketStore(DownState())

        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.issue(STEP_UP) if operation == "issue" else getattr(store, operation)("x" * 43)


class TestStagedSignIns:
    def test_a_staged_sign_in_reads_back_until_it_is_discarded_and_only_for_its_session(self):
        store = StagedSignInStore(MemoryState())
        store.stage(SESSION_ID, STAGED, ttl_seconds=600)

        assert store.read(SESSION_ID) == STAGED
        assert store.read(SESSION_ID) == STAGED
        assert store.read(uuid.uuid4()) is None
        store.discard(SESSION_ID)
        assert store.read(SESSION_ID) is None

    def test_the_record_is_stored_encrypted_under_a_key_that_hides_the_session(self):
        state = MemoryState()

        StagedSignInStore(state).stage(SESSION_ID, STAGED, ttl_seconds=123)

        (key,) = _keys(state)
        payload = state.get(key)
        assert str(SESSION_ID) not in key
        for value in ("subject-secret-1", "alice@example.com", "Alice Example", str(USER_ID)):
            assert value.encode() not in payload

    def test_a_record_that_cannot_be_decrypted_reads_as_missing(self, caplog):
        state = MemoryState()
        store = StagedSignInStore(state)
        store.stage(SESSION_ID, STAGED, ttl_seconds=600)
        state.set(_keys(state)[0], b"not a fernet token", ttl_seconds=600)

        with caplog.at_level(logging.WARNING):
            assert store.read(SESSION_ID) is None

        assert "could not be read" in caplog.text

    @pytest.mark.parametrize("operation", ["stage", "read"])
    def test_an_outage_fails_closed(self, operation):
        store = StagedSignInStore(DownState())

        with pytest.raises(core_attempt_state.StateUnavailableError):
            if operation == "stage":
                store.stage(SESSION_ID, STAGED, ttl_seconds=600)
            else:
                store.read(SESSION_ID)

    def test_an_outage_while_discarding_leaves_the_record_to_expire(self, caplog):
        with caplog.at_level(logging.WARNING):
            StagedSignInStore(DownState()).discard(SESSION_ID)

        assert "left to expire" in caplog.text


class TestRefreshClaims:
    def test_one_refresh_of_a_session_holds_the_claim_until_it_is_released(self):
        claims = refresh_claim_store.IdpRefreshClaimStore(MemoryState())

        assert claims.claim(SESSION_ID) is True
        assert claims.claim(SESSION_ID) is False
        assert claims.claim(uuid.uuid4()) is True
        claims.release(SESSION_ID)
        assert claims.claim(SESSION_ID) is True

    def test_an_outage_lets_the_refresh_go_on_and_the_release_fail_quietly(self, caplog):
        claims = refresh_claim_store.IdpRefreshClaimStore(DownState())

        with caplog.at_level(logging.WARNING):
            assert claims.claim(SESSION_ID) is True
            claims.release(SESSION_ID)

        assert "refreshing anyway" in caplog.text
        assert "expires on its own" in caplog.text


class TestLogoutTokenReplay:
    def test_a_token_is_accepted_once_and_a_release_makes_its_retry_acceptable(self):
        state = MemoryState()

        assert logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti-1", 120) is True
        assert logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti-1", 120) is False
        logout_token_replay_store.release_logout_token(state, IDP_ID, "jti-1")
        assert logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti-1", 120) is True

    def test_providers_and_tokens_do_not_block_each_other(self):
        state = MemoryState()
        logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti-1", 120)

        assert logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti-2", 120) is True
        assert logout_token_replay_store.claim_logout_token(state, uuid.uuid4(), "jti-1", 120) is True

    def test_a_jti_the_provider_chose_never_becomes_part_of_a_key_as_it_is(self):
        state = MemoryState()

        logout_token_replay_store.claim_logout_token(state, IDP_ID, "jti:with/odd chars", 95)

        (key,) = _keys(state)
        assert "odd" not in key

    def test_an_outage_refuses_the_token_rather_than_accept_it_unchecked(self):
        state = DownState()

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            logout_token_replay_store.claim_logout_token(state, IDP_ID, "j", 120)
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            logout_token_replay_store.release_logout_token(state, IDP_ID, "j")
