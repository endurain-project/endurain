"""Tests for websocket.integration_service module."""

from datetime import UTC, datetime

import pytest
from jasil.testing import capture_hints, install_test_platform

import core.job_status as core_job_status
import modules.websocket.integration_service as websocket_integration


@pytest.fixture
def hints(tmp_path):
    import jasil.testing as jasil_testing

    platform = install_test_platform(tmp_path)
    yield capture_hints(platform)
    jasil_testing.reset_all()


def test_a_push_is_published_for_the_user_key(hints):
    websocket_integration.push_to_user(7, {"message": "NEW", "notification_id": 3})

    assert hints == [("user:7", {"message": "NEW", "notification_id": 3})]


def test_a_push_the_channel_refuses_is_logged_not_raised(hints):
    websocket_integration.push_to_user(7, {"message": object()})

    assert hints == []


def test_an_oversized_push_is_dropped_not_raised(hints):
    websocket_integration.push_to_user(7, {"message": "x" * 10_000})

    assert hints == []


def test_a_job_hint_names_the_job_and_reaches_the_users_key(hints):
    websocket_integration.push_job_changed(7, "job-1", "garmin_link")

    assert hints == [("user:7", {"message": "JOB_STATUS_CHANGED", "job_id": "job-1", "kind": "garmin_link"})]


def test_a_job_is_announced_to_the_user_who_started_it(hints):
    job = core_job_status.JobRef(
        id="job-2", kind="user_deletion", owner_id=3, subject="9:account", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    websocket_integration.announce_job(job)

    assert hints == [("user:3", {"message": "JOB_STATUS_CHANGED", "job_id": "job-2", "kind": "user_deletion"})]
