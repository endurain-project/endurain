"""Tests for the out-of-range weight BMI migration (revision 38)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/38_clear_out_of_range_weight_bmi.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("clear_out_of_range_weight_bmi", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "4f2b8c6e1a93"


def test_upgrade_clears_only_the_bmis_outside_the_valid_range() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "health_weight",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bmi", sa.Numeric(10, 2), nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {"id": 1, "bmi": 163.27, "version": 1},
                {"id": 2, "bmi": -1, "version": 1},
                {"id": 3, "bmi": 100, "version": 1},
                {"id": 4, "bmi": 0, "version": 1},
                {"id": 5, "bmi": None, "version": 1},
            ],
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        stored = dict(connection.execute(sa.select(table.c.id, table.c.bmi)).all())
        versions = dict(connection.execute(sa.select(table.c.id, table.c.version)).all())
    engine.dispose()

    assert stored[1] is None
    assert stored[2] is None
    assert stored[3] == pytest.approx(100)
    assert stored[4] == pytest.approx(0)
    assert stored[5] is None
    assert versions == {1: 2, 2: 2, 3: 1, 4: 1, 5: 1}


def test_downgrade_changes_nothing() -> None:
    assert _migration_module().downgrade() is None
