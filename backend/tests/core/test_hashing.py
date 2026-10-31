"""Tests for the shared hashing primitives."""

import hashlib

import core.hashing as core_hashing


class TestLogFingerprint:
    def test_is_the_first_eight_hex_characters_of_the_sha256_digest(self):
        value = "a-session-id"

        assert core_hashing.log_fingerprint(value) == hashlib.sha256(value.encode()).hexdigest()[:8]

    def test_is_stable_so_entries_about_one_value_can_be_matched(self):
        assert core_hashing.log_fingerprint("same") == core_hashing.log_fingerprint("same")

    def test_differs_between_values_and_never_contains_the_value(self):
        first, second = "session-aaaaaaaa", "session-bbbbbbbb"

        assert core_hashing.log_fingerprint(first) != core_hashing.log_fingerprint(second)
        assert first[:8] not in core_hashing.log_fingerprint(first)
