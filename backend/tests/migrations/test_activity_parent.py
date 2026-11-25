"""The activity parent revision links legs to a multisport parent, and its downgrade keeps the legs as activities."""

import uuid

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "86ddd2645a0c"
_REVISION = "daa50e9181bb"
_MULTISPORT = 48


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


def _insert_activity(
    engine, user_id: uuid.UUID, activity_type: int = 1, parent_id: uuid.UUID | None = None
) -> uuid.UUID:
    activity_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO activities (id, user_id, parent_activity_id, distance, activity_type, start_time, "
                "end_time, created_at, visibility, total_elapsed_time, total_timer_time, hide_start_time, "
                "hide_location, hide_map, hide_hr, hide_power, hide_cadence, hide_elevation, hide_speed, hide_pace, "
                "hide_laps, hide_workout_sets_steps, hide_gear, is_hidden) VALUES (:id, :user_id, :parent_id, 0, "
                ":type, now(), now(), now(), 0, 0, 0, false, false, false, false, false, false, false, false, false, "
                "false, false, false, false)"
            ),
            {"id": activity_id, "user_id": user_id, "type": activity_type, "parent_id": parent_id},
        )
    return activity_id


def _columns(engine) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns("activities")}


def _constraint_names(engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                sa.text("SELECT conname FROM pg_constraint WHERE conrelid = 'activities'::regclass")
            ).scalars()
        )


def _index_names(engine) -> set[str]:
    return {index["name"] for index in sa.inspect(engine).get_indexes("activities")}


def test_the_upgrade_adds_the_parent_column_its_cascading_key_its_index_and_its_check(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert "parent_activity_id" not in _columns(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert "parent_activity_id" in _columns(upgrade_db)
    assert "ix_activities_user_id_parent_activity_id" in _index_names(upgrade_db)
    assert "ck_activities_parent_not_self" in _constraint_names(upgrade_db)
    [foreign_key] = [
        key
        for key in sa.inspect(upgrade_db).get_foreign_keys("activities")
        if key["constrained_columns"] == ["parent_activity_id"]
    ]
    assert foreign_key["referred_table"] == "activities"
    assert foreign_key["options"]["ondelete"] == "CASCADE"


def test_deleting_a_parent_deletes_its_legs_and_an_activity_cannot_be_its_own_parent(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)
    user_id = _insert_user(upgrade_db)
    parent = _insert_activity(upgrade_db, user_id, _MULTISPORT)
    leg = _insert_activity(upgrade_db, user_id, parent_id=parent)

    with pytest.raises(sa.exc.IntegrityError), upgrade_db.begin() as connection:
        connection.execute(sa.text("UPDATE activities SET parent_activity_id = id WHERE id = :id"), {"id": leg})
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("DELETE FROM activities WHERE id = :id"), {"id": parent})

    with upgrade_db.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM activities WHERE id = :id"), {"id": leg}).scalar() == 0


def test_the_downgrade_drops_the_parents_and_keeps_their_legs_as_activities(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)
    user_id = _insert_user(upgrade_db)
    parent = _insert_activity(upgrade_db, user_id, _MULTISPORT)
    leg = _insert_activity(upgrade_db, user_id, parent_id=parent)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert "parent_activity_id" not in _columns(upgrade_db)
    assert "ix_activities_user_id_parent_activity_id" not in _index_names(upgrade_db)
    assert "ck_activities_parent_not_self" not in _constraint_names(upgrade_db)
    with upgrade_db.connect() as connection:
        remaining = connection.execute(sa.text("SELECT id FROM activities")).scalars().all()
    assert remaining == [leg]
