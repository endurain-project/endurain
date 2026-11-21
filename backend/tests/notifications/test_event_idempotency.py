"""A redelivered event creates its notification once, even when deliveries overlap."""

import threading
import time
import uuid

from sqlalchemy import column, func, select, table

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user

pg_stat_activity = table("pg_stat_activity", column("datname"), column("wait_event_type"), column("query"))
waiting_on_lock = (
    (pg_stat_activity.c.datname == func.current_database())
    & (pg_stat_activity.c.wait_event_type == "Lock")
    & pg_stat_activity.c.query.like("%INSERT INTO notifications%")
)


def test_concurrent_deliveries_of_one_event_create_one_notification(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    event_id = str(uuid.uuid4())
    barrier = threading.Barrier(6)
    created: list[bool] = []

    def deliver() -> None:
        barrier.wait()
        with committed_sessions() as db:
            _, was_created = notifications_crud.create_notification_once(
                notifications_schema.NotificationCreate(
                    user_id=user.id,
                    type=notifications_constants.NotificationType.NEW_ACTIVITY,
                    source_event_id=event_id,
                    options={"activity_id": str(uuid.uuid4())},
                ),
                db,
            )
            db.commit()
            created.append(was_created)

    threads = [threading.Thread(target=deliver) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert created.count(True) == 1
    assert len(created) == 6
    with committed_sessions() as db:
        assert db.scalar(select(func.count()).select_from(notifications_models.Notification)) == 1


def test_deleting_notifications_naming_a_user_matches_the_json_reference(committed_sessions):
    with committed_sessions() as db:
        first, second, named = make_user(db), make_user(db), make_user(db)
        for owner, referenced in [(first, named), (second, named), (first, second), (second, first)]:
            make_notification_of(
                db,
                owner.id,
                notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST,
                {"user_id": str(referenced.id), "user_name": "A", "user_username": "a"},
            )
        db.commit()

    with committed_sessions() as db:
        assert notifications_crud.delete_notifications_naming_user(named.id, db) == 2
        db.commit()
        assert db.scalar(select(func.count()).select_from(notifications_models.Notification)) == 2


def test_a_delivery_that_loses_the_insert_race_returns_the_winners_notification(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    create = notifications_schema.NotificationCreate(
        user_id=user.id,
        type=notifications_constants.NotificationType.NEW_ACTIVITY,
        source_event_id=str(uuid.uuid4()),
        options={"activity_id": str(uuid.uuid4())},
    )
    outcome: list[tuple[uuid.UUID, bool]] = []

    def loser() -> None:
        with committed_sessions() as db:
            notification, was_created = notifications_crud.create_notification_once(create, db)
            db.commit()
            outcome.append((notification.id, was_created))

    with committed_sessions() as winner_db, committed_sessions() as observer:
        winner, was_created = notifications_crud.create_notification_once(create, winner_db)
        thread = threading.Thread(target=loser)
        thread.start()
        # The loser's insert waits on the winner's uncommitted row until the winner commits.
        deadline = time.monotonic() + 20
        while not observer.scalar(select(func.count()).select_from(pg_stat_activity).where(waiting_on_lock)):
            assert time.monotonic() < deadline
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            observer.rollback()
            threading.Event().wait(0.02)
        winner_db.commit()
        thread.join(timeout=20)

    assert was_created is True
    assert outcome == [(winner.id, False)]
    with committed_sessions() as db:
        assert db.scalar(select(func.count()).select_from(notifications_models.Notification)) == 1
