"""Tests for the time budget of a durable pass of long work."""

import pytest

import core.config as core_config
import core.job_queues as core_job_queues


@pytest.mark.parametrize(("lease", "expected"), [(300, 100.0), (3000, 1000.0), (30, 30.0)])
def test_the_pass_budget_is_a_third_of_the_lease_with_a_floor(monkeypatch, lease, expected):
    monkeypatch.setattr(core_config.settings, "JOBS_LEASE_SECONDS", lease)

    assert core_job_queues.durable_pass_seconds() == expected
