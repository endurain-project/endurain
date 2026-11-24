"""The v0.22 upgrade gate refuses while a v0.21 data migration is pending, on the real Alembic history."""

import uuid

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_ALL_FOUR = (11, 12, 13, 14)


def _insert_users(engine, count: int) -> None:
    """Add users, the minimum that makes the gate treat the database as an install in use."""
    with engine.begin() as connection:
        for number in range(count):
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                    "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                    "VALUES (:id, 'Ada', :username, :email, 'us', true, false, true, 'female', 'admin', "
                    "'monday', 'metric', 'euro')"
                ),
                {"id": uuid.uuid4(), "username": f"ada{number}", "email": f"ada{number}@example.com"},
            )


def _record_migrations(engine, rows: dict[int, bool]) -> None:
    """Record data migrations as a v0.21.x install holds them, ``rows`` giving each one's executed state."""
    with engine.begin() as connection:
        for migration_id, executed in rows.items():
            connection.execute(
                sa.text(
                    "INSERT INTO migrations (id, name, description, executed) "
                    "VALUES (:id, 'v0.21.0', 'test', :executed) ON CONFLICT (id) DO UPDATE SET executed = :executed"
                ),
                {"id": migration_id, "executed": executed},
            )


def _upgrade_from_v0_21(engine, *, users: int, rows: dict[int, bool]) -> None:
    alembic_chain.upgrade(engine, alembic_chain.V0_21_HEAD)
    _insert_users(engine, users)
    _record_migrations(engine, rows)
    alembic_chain.upgrade(engine, "head")


def test_a_fresh_install_without_users_passes_with_every_migration_pending(upgrade_db):
    _upgrade_from_v0_21(upgrade_db, users=0, rows={migration_id: False for migration_id in (7, *_ALL_FOUR)})


def test_the_upgrade_passes_when_all_four_data_migrations_are_executed(upgrade_db):
    _upgrade_from_v0_21(upgrade_db, users=1, rows=dict.fromkeys((7, *_ALL_FOUR), True))


def test_the_upgrade_names_the_absent_and_pending_migrations_in_order(upgrade_db):
    rows = {migration_id: True for migration_id in _ALL_FOUR if migration_id != 14}
    rows[12] = False

    with pytest.raises(RuntimeError) as error:
        _upgrade_from_v0_21(upgrade_db, users=1, rows=rows)

    assert str(error.value).startswith("Data migrations 12, 14 ")
    assert "v0.21.x" in str(error.value)


def test_every_data_migration_missing_is_named(upgrade_db):
    with pytest.raises(RuntimeError, match=r"Data migrations 11, 12, 13, 14 "):
        _upgrade_from_v0_21(upgrade_db, users=2, rows={})
