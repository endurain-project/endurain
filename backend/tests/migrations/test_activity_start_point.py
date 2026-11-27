"""The activity start point revision adds the nullable start latitude and longitude, and the downgrade drops them."""

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "3c1f5a7d9e24"
_REVISION = "5b8e2d4f6a13"
_COLUMNS = {"start_latitude", "start_longitude"}


def _columns(engine) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(engine).get_columns("activities")}


def test_the_upgrade_adds_two_nullable_double_precision_columns_with_comments(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert not _COLUMNS & set(_columns(upgrade_db))

    alembic_chain.upgrade(upgrade_db, _REVISION)

    columns = _columns(upgrade_db)
    for name in _COLUMNS:
        assert columns[name]["nullable"] is True
        assert isinstance(columns[name]["type"], sa.Double | sa.Float)
        assert "degrees" in columns[name]["comment"]


def test_the_downgrade_drops_the_columns(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert not _COLUMNS & set(_columns(upgrade_db))
