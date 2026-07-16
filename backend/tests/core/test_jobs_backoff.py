"""Tests for the durable-job retry backoff schedule."""

import infra.jobs.backoff as jobs_backoff


class TestBackoffSeconds:
    def test_first_retry_uses_base(self):
        assert jobs_backoff.backoff_seconds(1, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 5.0

    def test_zero_or_negative_attempts_use_base(self):
        assert jobs_backoff.backoff_seconds(0, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 5.0
        assert jobs_backoff.backoff_seconds(-3, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 5.0

    def test_exponential_growth(self):
        assert jobs_backoff.backoff_seconds(2, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 10.0
        assert jobs_backoff.backoff_seconds(3, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 20.0
        assert jobs_backoff.backoff_seconds(4, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 40.0

    def test_clamped_to_max(self):
        assert jobs_backoff.backoff_seconds(20, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 3600.0

    def test_large_attempts_do_not_overflow(self):
        # The exponent is capped so a huge attempts value stays at the ceiling.
        assert jobs_backoff.backoff_seconds(100_000, base_seconds=5.0, max_seconds=3600.0, jitter=False) == 3600.0

    def test_jitter_stays_within_half_to_full_of_the_deterministic_delay(self):
        # attempts=3 => deterministic 5 * 2**2 = 20; equal jitter keeps [10, 20].
        for _ in range(100):
            delay = jobs_backoff.backoff_seconds(3, base_seconds=5.0, max_seconds=3600.0)
            assert 10.0 <= delay <= 20.0

    def test_jitter_is_on_by_default(self):
        # With jitter the value is (almost surely) below the deterministic ceiling.
        samples = {jobs_backoff.backoff_seconds(5, base_seconds=5.0, max_seconds=3600.0) for _ in range(50)}
        assert any(sample < 80.0 for sample in samples)
