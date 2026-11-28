"""The revision deletes the stored duplicate-activity notifications and no other type; its downgrade is a no-op."""

import uuid

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "4f8c2b6d1a93"
_REVISION = "6a1d9c4e7b25"
_NEW_ACTIVITY = 1
_DUPLICATE_ACTIVITY = 2
_GARMIN_TOKEN_EXPIRED = 21


def _insert_user(engine) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                "VALUES (:id, 'Ada', :username, :email, 'us', true, false, true, 'female', 'regular', "
                "'monday', 'metric', 'euro')"
            ),
            {"id": user_id, "username": f"u{user_id.hex[:12]}", "email": f"{user_id.hex[:12]}@example.com"},
        )
    return user_id


def _notify(engine, user_id: uuid.UUID, notification_type: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO notifications (id, user_id, type, read, options, created_at) "
                "VALUES (gen_random_uuid(), :user_id, :type, false, '{}', now())"
            ),
            {"user_id": user_id, "type": notification_type},
        )


def _types(engine) -> list[int]:
    with engine.connect() as connection:
        return sorted(connection.execute(sa.text("SELECT type FROM notifications")).scalars())


def test_the_upgrade_deletes_the_duplicate_notifications_of_every_user_and_keeps_the_rest(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    first, second = _insert_user(upgrade_db), _insert_user(upgrade_db)
    for user_id in (first, second):
        _notify(upgrade_db, user_id, _DUPLICATE_ACTIVITY)
        _notify(upgrade_db, user_id, _DUPLICATE_ACTIVITY)
        _notify(upgrade_db, user_id, _NEW_ACTIVITY)
    _notify(upgrade_db, first, _GARMIN_TOKEN_EXPIRED)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _types(upgrade_db) == [_NEW_ACTIVITY, _NEW_ACTIVITY, _GARMIN_TOKEN_EXPIRED]


def test_the_upgrade_of_an_inbox_without_them_changes_nothing(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    _notify(upgrade_db, _insert_user(upgrade_db), _NEW_ACTIVITY)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _types(upgrade_db) == [_NEW_ACTIVITY]


def test_the_downgrade_does_nothing_and_the_deleted_rows_stay_gone(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    user_id = _insert_user(upgrade_db)
    _notify(upgrade_db, user_id, _DUPLICATE_ACTIVITY)
    _notify(upgrade_db, user_id, _NEW_ACTIVITY)
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert _types(upgrade_db) == [_NEW_ACTIVITY]
