"""Tests for the per-account email cooldown."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState

import core.email_cooldown as core_email_cooldown


def test_the_first_email_is_allowed_and_a_repeat_is_not():
    state = MemoryState()

    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60) is True
    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60) is False


@pytest.mark.parametrize(("kind", "user_id"), [("other_kind", 1), ("password_reset", 2)])
def test_another_kind_or_account_has_its_own_cooldown(kind, user_id):
    state = MemoryState()
    core_email_cooldown.claim_email(state, "password_reset", 1, 60)

    assert core_email_cooldown.claim_email(state, kind, user_id, 60) is True


def test_the_claimant_that_holds_the_claim_may_claim_again_and_another_may_not():
    state = MemoryState()

    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60, claimant="event-1") is True
    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60, claimant="event-1") is True
    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60, claimant="event-2") is False
    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60) is False


def test_a_claim_that_expires_between_the_two_calls_is_taken_on_the_second_try():
    state = MagicMock()
    state.set_if_absent.side_effect = [False, True]
    state.get.return_value = None

    assert core_email_cooldown.claim_email(state, "password_reset", 1, 60, claimant="event-1") is True
    assert state.set_if_absent.call_count == 2
