"""Tests for the per-account email cooldown."""

import pytest

import core.email_cooldown as core_email_cooldown
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.clock import memory_state


def test_the_first_email_is_allowed_and_a_repeat_is_not():
    state = memory_state()

    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60) is True
    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60) is False


@pytest.mark.parametrize(("kind", "user_id"), [("other_kind", MOCK_USER_ID), ("password_reset", OTHER_USER_ID)])
def test_another_kind_or_account_has_its_own_cooldown(kind, user_id):
    state = memory_state()
    core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60)

    assert core_email_cooldown.claim_email(state, kind, user_id, 60) is True


def test_the_claimant_that_holds_the_claim_may_claim_again_and_another_may_not():
    state = memory_state()

    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60, claimant="event-1") is True
    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60, claimant="event-1") is True
    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60, claimant="event-2") is False
    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60) is False


def test_a_claim_that_expires_between_the_two_calls_is_taken_on_the_second_try():
    class ClaimThatExpiresBetweenTheCalls:
        def __init__(self) -> None:
            self.writes = iter([False, True])

        def get(self, key):
            return None

        def set_if_absent(self, key, value, ttl):
            return next(self.writes)

    state = ClaimThatExpiresBetweenTheCalls()

    assert core_email_cooldown.claim_email(state, "password_reset", MOCK_USER_ID, 60, claimant="event-1") is True
    assert next(state.writes, "used up") == "used up"
