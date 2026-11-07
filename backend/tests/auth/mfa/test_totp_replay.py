"""Tests for the single-use rule on accepted TOTP time steps."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pyotp
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.mfa.totp_replay_store as totp_replay_store

_SECRET = "JBSWY3DPEHPK3PXP"
_NOW = datetime(2026, 1, 1, 12, 0, 15, tzinfo=UTC)


class TestMatchingTotpStep:
    def test_the_current_code_matches_the_current_step(self):
        totp = pyotp.TOTP(_SECRET)
        step = totp.timecode(_NOW)

        assert totp_replay_store.matching_totp_step(_SECRET, totp.at(_NOW), _NOW) == step

    @pytest.mark.parametrize("offset", [-1, 1])
    def test_the_neighbouring_steps_are_accepted_for_clock_drift(self, offset):
        totp = pyotp.TOTP(_SECRET)
        step = totp.timecode(_NOW) + offset

        assert totp_replay_store.matching_totp_step(_SECRET, totp.generate_otp(step), _NOW) == step

    def test_a_code_two_steps_away_does_not_match(self):
        totp = pyotp.TOTP(_SECRET)

        assert totp_replay_store.matching_totp_step(_SECRET, totp.generate_otp(totp.timecode(_NOW) + 2), _NOW) is None

    def test_a_wrong_code_does_not_match(self):
        assert totp_replay_store.matching_totp_step(_SECRET, "000000", _NOW) in (
            None,
            pyotp.TOTP(_SECRET).timecode(_NOW),
        )
        wrong = "000000" if pyotp.TOTP(_SECRET).at(_NOW) != "000000" else "111111"
        assert totp_replay_store.matching_totp_step(_SECRET, wrong, _NOW) is None


class TestClaimTotpStep:
    def test_a_step_is_accepted_once(self):
        state = MemoryState()

        assert totp_replay_store.claim_totp_step(state, 7, 100) is True
        assert totp_replay_store.claim_totp_step(state, 7, 100) is False

    def test_steps_and_users_do_not_block_each_other(self):
        state = MemoryState()
        totp_replay_store.claim_totp_step(state, 7, 100)

        assert totp_replay_store.claim_totp_step(state, 7, 101) is True
        assert totp_replay_store.claim_totp_step(state, 8, 100) is True

    def test_an_unreachable_store_fails_closed_as_unavailable(self):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            totp_replay_store.claim_totp_step(state, 7, 100)
