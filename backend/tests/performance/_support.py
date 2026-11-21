"""Shared by the performance guards: counting the SQL a request sends and arranging a user's data at a given size."""

import contextlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.activities.activity_streams.constants as streams_constants
import modules.gears.gear.models as gear_models
import modules.gears.gear_components.models as gear_component_models
import modules.health.health_weight.models as weight_models
import modules.notifications.constants as notifications_constants
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
from tests._factories import activities as activity_factories
from tests._factories import followers as follower_factories
from tests._factories import gears as gear_factories
from tests._factories import health as health_factories
from tests._factories import jobs as job_factories
from tests._factories import notifications as notification_factories
from tests._factories import sync as sync_factories
from tests._factories import users as user_factories

#: Stamp that is old enough for ``/sync`` to report a record.
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)

_STREAM_TYPES = tuple(streams_constants.ActivityStreamType)


@dataclass(frozen=True)
class Captured:
    """One statement a request sent.

    Attributes:
        statement: The SQL text with its driver placeholders.
        parameters: The values bound to the placeholders.
    """

    statement: str
    parameters: object

    @property
    def shape(self) -> str:
        """The statement with its parameters left out, for comparing two requests."""
        return " ".join(self.statement.split())


@contextlib.contextmanager
def captured_statements() -> Iterator[list[Captured]]:
    """Record every statement the application's engine executes while the block runs.

    Yields:
        The list the statements are appended to, in order.
    """
    seen: list[Captured] = []

    def record(_conn, _cursor, statement, parameters, _context, _executemany) -> None:
        seen.append(Captured(statement, parameters))

    event.listen(core_database.engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(core_database.engine, "before_cursor_execute", record)


def local_today(db: Session, user_id: uuid.UUID):
    """Return today's date in the user's timezone, as the dashboard resolves it."""
    return users_integration.local_today(user_id, db)


def make_followee(db: Session, follower: users_schema.UserRead) -> users_schema.UserRead:
    """Stage a user whom ``follower`` follows with an accepted request (flushed, not committed)."""
    followee = user_factories.make_user(db)
    follower_factories.make_follow(db, follower.id, followee.id, accepted=True)
    return followee


def arrange_followed_feed(db: Session, user: users_schema.UserRead, followees: int, per_followee: int) -> None:
    """Give a user ``followees`` accepted followees with ``per_followee`` follower-visible activities each."""
    for _ in range(followees):
        followee = make_followee(db, user)
        for index in range(per_followee):
            activity_factories.make_activity_at(
                db,
                followee.id,
                activity_factories.DEFAULT_START + timedelta(hours=3 * index),
                visibility=activity_constants.ActivityVisibility.FOLLOWERS,
            )


def arrange_activities(
    db: Session, user_id: uuid.UUID, count: int, *, children: int = 1, with_gear: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """Stage ``count`` activities for a user, each with ``children`` laps, sets and steps, streams and media.

    Args:
        db: Database session.
        user_id: The owner.
        count: How many activities.
        children: How many laps, sets, workout steps and media records each activity holds.
        with_gear: The gear the activities were recorded with, if any.

    Returns:
        The activity ids, oldest first.
    """
    ids = []
    for index in range(count):
        activity = activity_factories.make_activity_at(
            db,
            user_id,
            activity_factories.DEFAULT_START + timedelta(hours=3 * index),
            name=f"Run {index}",
            gear_id=with_gear,
        )
        if not children:
            ids.append(activity.id)
            continue
        activity_factories.make_laps(db, activity, [{"start_time": activity.start_time} for _ in range(children)])
        activity_factories.make_sets(
            db,
            activity,
            [
                {"start_time": activity.start_time.isoformat(), "duration": 30.0, "set_type": "active"}
                for _ in range(children)
            ],
        )
        activity_factories.make_workout_steps(
            db, activity, [{"message_index": step, "duration_type": "time"} for step in range(children)]
        )
        for stream_type in _STREAM_TYPES[: min(children, len(_STREAM_TYPES))]:
            activity_factories.make_stream(
                db, activity, stream_type.stored, [{"time": "2025-03-10T08:00:00", "hr": 120}]
            )
        for number in range(children):
            activity_factories.make_activity_media(db, activity, f"{activity.id}/{number}.jpg")
        ids.append(activity.id)
    return ids


def arrange_weights(db: Session, user_id: uuid.UUID, count: int) -> list[uuid.UUID]:
    """Stage ``count`` weight records on consecutive days ending at the user's today."""
    today = local_today(db, user_id)
    return [
        health_factories.make_health_weight(
            db, user_id, date=today - timedelta(days=offset + 1), weight_kg=70.0 + offset
        ).id
        for offset in range(count)
    ]


def arrange_dashboard(db: Session, user_id: uuid.UUID, count: int) -> None:
    """Stage ``count`` bowel movements today and one record of each other kind the dashboard reads."""
    today = local_today(db, user_id)
    for index in range(count):
        health_factories.make_health_poop(
            db, user_id, date_time=datetime.combine(today, datetime.min.time(), UTC) + timedelta(minutes=index)
        )
    health_factories.make_health_weight(db, user_id, date=today)
    health_factories.make_health_steps(db, user_id, date=today)
    health_factories.make_health_water(db, user_id, date=today)
    health_factories.make_health_sleep(db, user_id, date=today)


def arrange_gears(db: Session, user_id: uuid.UUID, count: int, *, components: int = 2) -> list[uuid.UUID]:
    """Stage ``count`` gears with ``components`` components each."""
    ids = []
    for index in range(count):
        gear = gear_factories.make_gear(db, user_id, nickname=f"Bike {index}")
        for part in range(components):
            gear_factories.make_gear_component(db, user_id, gear.id, model=f"Part {part}")
        ids.append(gear.id)
    return ids


def arrange_notifications(db: Session, user_id: uuid.UUID, count: int) -> None:
    """Stage ``count`` notifications, oldest first, every other one read."""
    for index in range(count):
        notification_factories.make_notification_of(
            db,
            user_id,
            notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED,
            read=index % 2 == 0,
            created_at=LONG_AGO + timedelta(minutes=index),
        )


def arrange_jobs(db: Session, user_id: uuid.UUID, count: int) -> None:
    """Stage ``count`` pending ingestion jobs accepted a minute apart."""
    for index in range(count):
        job_factories.make_ingestion_job_at(db, user_id, LONG_AGO + timedelta(minutes=index))


def arrange_syncable(db: Session, user_id: uuid.UUID, count: int) -> None:
    """Stage ``count`` activities, weights, gears and components, all stamped old enough for ``/sync`` to report."""
    activities = arrange_activities(db, user_id, count, children=0)
    weights = arrange_weights(db, user_id, count)
    gears = arrange_gears(db, user_id, count, components=1)
    sync_factories.restamp(db, activity_models.Activity, activities, LONG_AGO)
    sync_factories.restamp(db, weight_models.HealthWeight, weights, LONG_AGO)
    sync_factories.restamp(db, gear_models.Gear, gears, LONG_AGO)
    component_ids = db.scalars(
        select(gear_component_models.GearComponents.id).where(gear_component_models.GearComponents.user_id == user_id)
    ).all()
    sync_factories.restamp(db, gear_component_models.GearComponents, component_ids, LONG_AGO)
