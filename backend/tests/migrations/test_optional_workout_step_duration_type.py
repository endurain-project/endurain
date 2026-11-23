"""The optional workout step duration type revision lets a step have none, and its downgrade drops such steps."""

import uuid

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "8d2f61b0c7a4"
_REVISION = "3c9e5a7d1f20"


def _insert_activity(engine) -> uuid.UUID:
    user_id, activity_id = uuid.uuid4(), uuid.uuid4()
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
        connection.execute(
            sa.text(
                "INSERT INTO activities (id, user_id, distance, activity_type, start_time, end_time, created_at, "
                "visibility, total_elapsed_time, total_timer_time, hide_start_time, hide_location, hide_map, hide_hr, "
                "hide_power, hide_cadence, hide_elevation, hide_speed, hide_pace, hide_laps, hide_workout_sets_steps, "
                "hide_gear, is_hidden) VALUES (:id, :user_id, 0, 1, now(), now(), now(), 0, 0, 0, false, false, false, "
                "false, false, false, false, false, false, false, false, false, false)"
            ),
            {"id": activity_id, "user_id": user_id},
        )
    return activity_id


def _insert_step(engine, activity_id: uuid.UUID, message_index: int, duration_type: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO activity_workout_steps (id, activity_id, message_index, duration_type) "
                "VALUES (:id, :activity_id, :message_index, :duration_type)"
            ),
            {
                "id": uuid.uuid4(),
                "activity_id": activity_id,
                "message_index": message_index,
                "duration_type": duration_type,
            },
        )


def _steps(engine, activity_id: uuid.UUID) -> list[tuple[int, str | None]]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT message_index, duration_type FROM activity_workout_steps WHERE activity_id = :a "
                "ORDER BY message_index"
            ),
            {"a": activity_id},
        )
        return [(row.message_index, row.duration_type) for row in rows]


def test_the_upgrade_keeps_every_step_and_lets_a_step_have_no_duration_type(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    activity_id = _insert_activity(upgrade_db)
    _insert_step(upgrade_db, activity_id, 0, "time")

    alembic_chain.upgrade(upgrade_db, _REVISION)
    _insert_step(upgrade_db, activity_id, 1, None)

    assert _steps(upgrade_db, activity_id) == [(0, "time"), (1, None)]


def test_the_downgrade_deletes_the_steps_without_a_duration_type_and_requires_one_again(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)
    activity_id = _insert_activity(upgrade_db)
    _insert_step(upgrade_db, activity_id, 0, "time")
    _insert_step(upgrade_db, activity_id, 1, None)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert _steps(upgrade_db, activity_id) == [(0, "time")]
    with upgrade_db.connect() as connection:
        nullable = connection.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'activity_workout_steps' AND column_name = 'duration_type'"
            )
        ).scalar_one()
    assert nullable == "NO"
