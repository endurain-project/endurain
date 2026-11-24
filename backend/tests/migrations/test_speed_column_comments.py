"""The speed column comments revision states meters per second, and its downgrade restores the old comments."""

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "3c9e5a7d1f20"
_REVISION = "86ddd2645a0c"


def _speed_comments(engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT a.attname, col_description(a.attrelid, a.attnum) AS comment "
                "FROM pg_attribute a WHERE a.attrelid = 'activities'::regclass "
                "AND a.attname IN ('average_speed', 'max_speed')"
            )
        )
        return {row.attname: row.comment for row in rows}


def test_the_upgrade_comments_the_speed_columns_as_meters_per_second(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert _speed_comments(upgrade_db) == {
        "average_speed": "Average speed seconds per meter (s/m)",
        "max_speed": "Max speed seconds per meter (s/m)",
    }

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert _speed_comments(upgrade_db) == {
        "average_speed": "Average speed in meters per second (m/s)",
        "max_speed": "Max speed in meters per second (m/s)",
    }


def test_the_downgrade_restores_the_seconds_per_meter_comments(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert _speed_comments(upgrade_db) == {
        "average_speed": "Average speed seconds per meter (s/m)",
        "max_speed": "Max speed seconds per meter (s/m)",
    }
