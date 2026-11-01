"""Tests for the per-account email cooldown."""

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
