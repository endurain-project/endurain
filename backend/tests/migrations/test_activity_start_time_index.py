"""The start time index revision builds and drops ``ix_activities_user_id_start_time`` concurrently."""

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "9e3b7a2c5d18"
_REVISION = "4f8c2b6d1a93"
_INDEX = "ix_activities_user_id_start_time"


def _indexes(engine) -> dict[str, dict]:
    return {index["name"]: index for index in sa.inspect(engine).get_indexes("activities")}


def test_the_upgrade_builds_a_valid_index_on_the_user_and_the_start(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert _INDEX not in _indexes(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _indexes(upgrade_db)[_INDEX]["column_names"] == ["user_id", "start_time"]
    with upgrade_db.connect() as connection:
        valid = connection.execute(
            sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"), {"name": _INDEX}
        ).scalar_one()
    assert valid is True


def test_the_upgrade_replaces_an_index_a_failed_build_left_behind(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    with upgrade_db.begin() as connection:
        connection.execute(sa.text(f"CREATE INDEX {_INDEX} ON activities (user_id)"))

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _indexes(upgrade_db)[_INDEX]["column_names"] == ["user_id", "start_time"]


def test_the_downgrade_drops_the_index(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert _INDEX not in _indexes(upgrade_db)
