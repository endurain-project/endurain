"""Tests for users.subscribers: the durable entry points of a queued account deletion."""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from jasil.events import Event, new_event

import modules.users.users.events as users_events
import modules.users.users.subscribers as users_subscribers

_MODULE = "modules.users.users.subscribers"


def _event(retry_count: int = 0, max_attempts: int | None = None) -> Event:
    event = new_event(users_events.USERS_DELETION_REQUESTED, {"user_id": 4}, source="test", retry_count=retry_count)
    return replace(event, max_attempts=max_attempts)


@pytest.fixture
def platform():
    platform = MagicMock()
    with patch(f"{_MODULE}.platform_runtime.get_active_platform", return_value=platform):
        yield platform


def test_the_durable_handler_runs_the_deletion_the_event_names(platform):
    with patch(f"{_MODULE}.users_deletion_job_service.run_deletion") as run:
        users_subscribers.process_deletion_requested_for_event(_event())

    assert run.call_args.args[0].user_id == 4
    assert run.call_args.args[2] is platform.storage


@pytest.mark.parametrize(("retry_count", "max_attempts", "will_retry"), [(0, 3, True), (3, 3, False)])
def test_only_an_attempt_with_attempts_left_asks_to_be_retried(platform, retry_count, max_attempts, will_retry):
    with patch(f"{_MODULE}.users_deletion_job_service.run_deletion") as run:
        users_subscribers.process_deletion_requested_for_event(_event(retry_count, max_attempts))

    assert run.call_args.kwargs["will_retry"] is will_retry


def test_a_dead_lettered_deletion_is_closed(platform):
    with patch(f"{_MODULE}.users_deletion_job_service.close_dead_lettered_deletion") as close:
        users_subscribers.on_deletion_requested_dead_letter(_event(), "boom")

    assert close.call_args.args[0].user_id == 4


def test_the_handler_is_registered_for_the_event():
    registry = MagicMock()

    users_subscribers.register_durable_handlers(registry)

    assert registry.register.call_args.args[:2] == (
        users_events.USERS_DELETION_REQUESTED,
        users_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID,
    )
