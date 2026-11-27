"""The activity samples revision creates the columnar table, with compressed arrays and CHECK constraints."""

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "069908f3eab8"
_REVISION = "3c1f5a7d9e24"


def _tables(engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _constraints(engine) -> set[str]:
    return {constraint["name"] for constraint in sa.inspect(engine).get_check_constraints("activity_samples")}


def test_the_upgrade_creates_the_table_with_its_constraints_and_lz4_arrays(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    assert "activity_samples" not in _tables(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION)

    assert "activity_samples" in _tables(upgrade_db)
    assert "ck_activity_samples_lat_lon_together" in _constraints(upgrade_db)
    assert "ck_activity_samples_heart_rate_len" in _constraints(upgrade_db)
    with upgrade_db.connect() as connection:
        compressions = connection.execute(
            sa.text(
                "SELECT attcompression FROM pg_attribute WHERE attrelid = 'activity_samples'::regclass "
                "AND attnum > 0 AND atttypid IN (SELECT oid FROM pg_type WHERE typcategory = 'A')"
            )
        ).scalars()
        assert set(compressions) == {"l"}


def test_the_downgrade_drops_the_table(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    assert "activity_samples" not in _tables(upgrade_db)
