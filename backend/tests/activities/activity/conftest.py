"""Fixtures shared by the activity tests: committed users, a signed-in client and a way to arrange committed rows."""

from collections.abc import Callable
from typing import Any

import pytest

import modules.activities.activity.events as activity_events
import tests._factories.activities as activity_factories
from tests._factories.users import make_user


@pytest.fixture
def arrange(committed_sessions) -> Callable[[Callable[[Any], Any]], Any]:
    """Return a function that runs an arranging step in a session it commits, and returns the step's result."""

    def run(step: Callable[[Any], Any]) -> Any:
        with committed_sessions() as db:
            result = step(db)
            db.commit()
        return result

    return run


@pytest.fixture
def owner(arrange):
    """A committed user in UTC."""
    return arrange(lambda db: make_user(db, timezone="UTC"))


@pytest.fixture
def other(arrange):
    """A second committed user in UTC."""
    return arrange(lambda db: make_user(db, timezone="UTC"))


@pytest.fixture
def me(sign_in, owner):
    """The owner, signed in to the production application."""
    return sign_in(owner)


@pytest.fixture
def make_committed_activity(arrange):
    """Return a function that commits an activity for a user and returns it."""

    def make(user, **overrides):
        return arrange(lambda db: activity_factories.make_activity(db, user.id, **overrides))

    return make


@pytest.fixture
def published(_publish_local_platform) -> dict[str, list]:
    """The activity events the bus delivered so far, by event type (best-effort delivery runs inline on commit)."""
    delivered: dict[str, list] = {}
    for event_type in (
        activity_events.ACTIVITY_CREATED,
        activity_events.ACTIVITY_UPDATED,
        activity_events.ACTIVITY_DELETED,
    ):
        delivered[event_type] = []
        _publish_local_platform.events.subscribe(event_type, delivered[event_type].append)
    return delivered
