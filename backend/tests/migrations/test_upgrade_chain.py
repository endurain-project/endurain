"""The real Alembic history, run against an empty database: the v0.21 baseline and the v0.22 revisions on top of it."""

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

import migrations.startup as migrations_startup
from tests._helpers import alembic_chain

_RETIREMENT_REVISION = "50ac9225ce4f"
_HEAD_REVISION = "3c1f5a7d9e24"
_REPROCESS_MIGRATION = {15: False}
_DATA_MIGRATIONS = (11, 12, 13, 14)
_SUBSTRATE_TABLES = ("event_log", "event_outbox", "processing_jobs", "job_attempts", "job_workers")

#: The one row a fresh install holds in ``server_settings``: every column default the v0.21 head ends with.
_SERVER_SETTINGS_SEED = {
    "id": 1,
    "public_shareable_links": False,
    "public_shareable_links_user_info": False,
    "login_photo_set": False,
    "num_records_per_page": 25,
    "signup_enabled": False,
    "signup_require_admin_approval": False,
    "signup_require_email_verification": False,
    "sso_enabled": False,
    "local_login_enabled": True,
    "sso_auto_redirect": False,
    "tileserver_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "tileserver_attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    "map_background_color": "#dddddd",
    "password_length_regular_users": 15,
    "password_length_admin_users": 15,
    "tileserver_api_key": None,
    "units": "metric",
    "currency": "euro",
    "tileserver_regenerate_thumbnails_on_change": False,
    "geocoding_service": "nominatim",
    "geocoding_host": None,
    "geocoding_use_https": True,
    "geocoding_rate_limit": 1,
    "geocoding_api_key": None,
    "session_idle_timeout_enabled": True,
    "session_idle_timeout_hours": 72,
    "session_absolute_timeout_hours": 720,
    "access_token_expire_minutes": 15,
    "refresh_token_expire_days": 7,
    "read_notification_retention_days": 90,
    "version": 1,
    "api_key_max_lifetime_days": 365,
    "password_breach_check_enabled": False,
    "signup_sso_enabled": False,
    "require_mfa": "off",
}
_MAIL_SETTINGS_SEED = {
    "id": 1,
    "host": None,
    "port": 587,
    "security": "starttls",
    "username": None,
    "password": None,
    "from_address": None,
    "version": 1,
}


def _scalar(engine, statement: str):
    with engine.connect() as connection:
        return connection.execute(sa.text(statement)).scalar()


def _row(engine, table: str) -> dict:
    with engine.connect() as connection:
        return dict(connection.execute(sa.select(sa.text("*")).select_from(sa.table(table))).mappings().one())


def _migrations_state(engine) -> dict[int, bool]:
    with engine.connect() as connection:
        return {row.id: row.executed for row in connection.execute(sa.text("SELECT id, executed FROM migrations"))}


def _tables(engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _insert_user(engine) -> None:
    """Add one user, the minimum that makes the v0.22 gate treat the database as an install in use."""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                "VALUES (:id, 'Ada', 'ada', 'ada@example.com', 'us', true, false, true, 'female', 'admin', "
                "'monday', 'metric', 'euro')"
            ),
            {"id": uuid.uuid4()},
        )


def _set_data_migrations(engine, executed: dict[int, bool]) -> None:
    """Record data migrations 11 to 14 as a v0.21.x install holds them, ``executed`` giving each one's state."""
    with engine.begin() as connection:
        for migration_id, done in executed.items():
            connection.execute(
                sa.text(
                    "INSERT INTO migrations (id, name, description, executed) VALUES (:id, 'v0.21.0', 'test', :done)"
                ),
                {"id": migration_id, "done": done},
            )


def test_a_fresh_install_upgrades_to_head_and_matches_the_models(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []
    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _HEAD_REVISION


def test_the_baseline_alone_differs_from_the_models_only_where_v0_22_changes_the_schema_and_makes_no_substrate_table(
    upgrade_db,
):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_21_HEAD)

    differences = alembic_chain.schema_differences(upgrade_db)
    # An index difference is a tuple; a column difference is a list of the column's changes.
    indexes = {(entry[0], entry[1].name) for entry in differences if isinstance(entry, tuple) and "index" in entry[0]}
    added = {
        (entry[0], entry[2], getattr(entry[3], "name", None))
        for entry in differences
        if isinstance(entry, tuple) and entry[0] == "add_column"
    }
    foreign_keys = [entry[0] for entry in differences if isinstance(entry, tuple) and entry[0] == "add_fk"]
    columns = [
        (change[0], change[2], change[3], change[5], change[6])
        for entry in differences
        if isinstance(entry, list)
        for change in entry
    ]
    # The baseline's nickname index is ``lower(nickname)``, its workout step duration type is required, and its
    # speed columns are commented as seconds per meter.
    assert indexes == {
        ("remove_index", "uq_gear_user_nickname"),
        ("add_index", "uq_gear_user_nickname"),
        ("add_index", "ix_activities_user_id_parent_activity_id"),
        ("add_index", "ix_activities_analysis_version_id"),
    }
    # The baseline has no multisport parent column, nor the key on it, and no analysis version.
    assert added == {
        ("add_column", "activities", "parent_activity_id"),
        ("add_column", "activities", "analysis_version"),
    }
    assert foreign_keys == ["add_fk"]
    assert columns == [
        (
            "modify_comment",
            "activities",
            "average_speed",
            "Average speed seconds per meter (s/m)",
            "Average speed in meters per second (m/s)",
        ),
        (
            "modify_comment",
            "activities",
            "max_speed",
            "Max speed seconds per meter (s/m)",
            "Max speed in meters per second (m/s)",
        ),
        ("modify_nullable", "activity_workout_steps", "duration_type", False, True),
    ]
    tables = _tables(upgrade_db)
    assert not tables & {*_SUBSTRATE_TABLES, "uuid_migration_ids"}
    assert not {name for name in tables if name.startswith("jasil_")}
    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == alembic_chain.V0_21_HEAD


def test_a_fresh_install_holds_exactly_the_seed_rows(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    counts = {name: count for name, count in alembic_chain.row_counts(upgrade_db).items() if count}
    assert counts == {"mail_settings": 1, "migrations": 1, "server_settings": 1}
    assert _row(upgrade_db, "server_settings") == _SERVER_SETTINGS_SEED
    assert _row(upgrade_db, "mail_settings") == _MAIL_SETTINGS_SEED
    assert _migrations_state(upgrade_db) == _REPROCESS_MIGRATION


def test_the_baseline_seeds_the_rows_a_v0_21_install_has_before_its_data_migrations_run(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_21_HEAD)

    assert _migrations_state(upgrade_db) == {7: True}
    assert _row(upgrade_db, "server_settings") == _SERVER_SETTINGS_SEED
    assert _row(upgrade_db, "mail_settings") == _MAIL_SETTINGS_SEED


def test_the_v0_22_upgrade_refuses_while_a_v0_21_data_migration_is_pending(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_21_HEAD)
    _insert_user(upgrade_db)
    _set_data_migrations(upgrade_db, {11: True, 12: True, 13: False, 14: True})
    before = _migrations_state(upgrade_db)

    with pytest.raises(RuntimeError, match=r"Data migrations 13 .*v0\.21\.x"):
        alembic_chain.upgrade(upgrade_db, "head")

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == alembic_chain.V0_21_HEAD
    assert _migrations_state(upgrade_db) == before


def test_the_v0_22_upgrade_retires_the_v0_21_data_migrations_once_they_have_all_run(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_21_HEAD)
    _insert_user(upgrade_db)
    _set_data_migrations(upgrade_db, dict.fromkeys(_DATA_MIGRATIONS, True))
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("CREATE TABLE uuid_migration_ids (old_id integer, new_id uuid)"))

    alembic_chain.upgrade(upgrade_db, "head")

    assert _migrations_state(upgrade_db) == _REPROCESS_MIGRATION
    assert _scalar(upgrade_db, "SELECT to_regclass('uuid_migration_ids')") is None
    assert _scalar(upgrade_db, "SELECT count(*) FROM users") == 1
    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _HEAD_REVISION


def test_startup_refuses_a_database_at_an_unknown_revision_before_any_revision_runs(upgrade_db, monkeypatch):
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO alembic_version VALUES ('d54bdd779392')"))
    monkeypatch.setattr(migrations_startup, "engine", upgrade_db)
    monkeypatch.chdir(Path(__file__).resolve().parents[2] / "app")

    with pytest.raises(RuntimeError, match=r"upgrades only from v0\.21\.x"):
        migrations_startup.run_alembic_upgrade()

    assert _tables(upgrade_db) == {"alembic_version"}
    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == "d54bdd779392"


def test_the_v0_21_data_migration_retirement_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _RETIREMENT_REVISION)

    with pytest.raises(NotImplementedError, match="restore the database from the backup"):
        alembic_chain.downgrade(upgrade_db, alembic_chain.V0_21_HEAD)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _RETIREMENT_REVISION


def test_the_baseline_cannot_be_downgraded(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_21_HEAD)

    with pytest.raises(NotImplementedError, match="restore the database from a backup"):
        alembic_chain.downgrade(upgrade_db, "base")

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == alembic_chain.V0_21_HEAD
