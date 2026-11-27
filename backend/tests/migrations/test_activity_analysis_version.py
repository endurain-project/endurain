"""The analysis version revision stamps activities with the analysis that computed them and queues the reprocess."""

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "daa50e9181bb"
_REVISION = "069908f3eab8"
_INDEX = "ix_activities_analysis_version_id"


def _columns(engine) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(engine).get_columns("activities")}


def _index_columns(engine) -> dict[str, list[str]]:
    return {index["name"]: index["column_names"] for index in sa.inspect(engine).get_indexes("activities")}


def _pending(engine) -> list[tuple]:
    with engine.connect() as connection:
        return [
            tuple(row) for row in connection.execute(sa.text("SELECT id, name, description, executed FROM migrations"))
        ]


def _insert_activity(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'Ada', 'ada', 'ada@example.com', 'us', true, false, "
                "true, 'female', 'regular', 'monday', 'metric', 'euro')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO activities (id, user_id, distance, activity_type, start_time, end_time, created_at, "
                "visibility, total_elapsed_time, total_timer_time, hide_start_time, hide_location, hide_map, hide_hr, "
                "hide_power, hide_cadence, hide_elevation, hide_speed, hide_pace, hide_laps, hide_workout_sets_steps, "
                "hide_gear, is_hidden) VALUES ('00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000001', 0, 1, now(), now(), now(), 0, 0, 0, false, false, false, "
                "false, false, false, false, false, false, false, false, false, false)"
            )
        )


def test_the_upgrade_adds_the_version_column_defaulting_existing_rows_to_zero(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    _insert_activity(upgrade_db)
    assert "analysis_version" not in _columns(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    column = _columns(upgrade_db)["analysis_version"]
    assert isinstance(column["type"], sa.SmallInteger)
    assert column["nullable"] is False
    assert column["comment"].startswith("The version of the file analysis")
    with upgrade_db.connect() as connection:
        assert connection.execute(sa.text("SELECT analysis_version FROM activities")).scalars().all() == [0]


def test_the_upgrade_adds_the_keyset_index_and_the_pending_reprocess_row(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert _pending(upgrade_db) == []

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _index_columns(upgrade_db)[_INDEX] == ["analysis_version", "id"]
    assert _pending(upgrade_db) == [
        (15, "v0.22.0", "Reprocess activities from their retained files with the v0.22 analysis", False)
    ]


def test_the_downgrade_removes_the_row_the_index_and_the_column(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert "analysis_version" not in _columns(upgrade_db)
    assert _INDEX not in _index_columns(upgrade_db)
    assert _pending(upgrade_db) == []
