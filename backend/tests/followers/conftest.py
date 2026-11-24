"""Fixtures shared by the followers tests: three users, the events the module publishes and the audit rows it writes."""

import uuid
from collections.abc import Callable

import jasil.runtime as jasil_runtime
import pytest
from jasil.audit.models import AuditLog
from jasil.events import Event
from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.followers.events as followers_events
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
from tests._factories.users import make_user


@pytest.fixture
def alice(db: Session) -> users_schema.UserRead:
    """An active user."""
    return make_user(db)


@pytest.fixture
def bob(db: Session) -> users_schema.UserRead:
    """An active user."""
    return make_user(db)


@pytest.fixture
def carol(db: Session) -> users_schema.UserRead:
    """An active user."""
    return make_user(db)


@pytest.fixture
def published() -> list[Event]:
    """The follower events published during the test, in order, as the bus delivers them."""
    events: list[Event] = []
    bus = jasil_runtime.get_active_platform().events
    for channel in (
        followers_events.FOLLOWER_REQUESTED,
        followers_events.FOLLOWER_ACCEPTED,
        followers_events.FOLLOWER_REQUEST_REMOVED,
    ):
        bus.subscribe(channel, events.append)
    return events


def audited(db: Session) -> list[tuple[str, str | None, str | None]]:
    """List the audit rows the followers package wrote as ``(action id, target id, target owner id)``, oldest first."""
    rows = db.scalars(
        select(AuditLog).where(AuditLog.action_id.like("followers.%")).order_by(AuditLog.occurred_at, AuditLog.id)
    ).all()
    return [(row.action_id, row.target_id, row.target_owner_id) for row in rows]


@pytest.fixture
def hide() -> Callable[[Session, uuid.UUID, str], None]:
    """Return a function that makes a user inactive (``"inactive"``) or awaiting approval (``"pending"``)."""

    def hide_user(db: Session, user_id: uuid.UUID, state: str) -> None:
        user = db.get(users_models.Users, user_id)
        assert user is not None
        user.active = state != "inactive"
        user.pending_admin_approval = state == "pending"
        db.flush()

    return hide_user
