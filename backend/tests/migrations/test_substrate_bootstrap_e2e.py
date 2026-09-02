"""End-to-end check of the substrate schema bootstrap against a real database.

The unit tests assert the call sequence. These run it, so a baseline that does
not match the schema this application's own history creates would fail here
rather than on a production boot.
"""

import pathlib

import jasil.migrations as jasil_migrations
import jasil.orm as jasil_orm
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

import core.migrations as core_migrations
from core.database import Base

BASELINE = core_migrations.SUBSTRATE_BASELINE_REVISION


def _bootstrap(engine) -> None:
    """Run the production bootstrap sequence against an arbitrary engine."""
    inspector = sa.inspect(engine)
    if jasil_migrations.db_revision(engine) is None and all(
        inspector.has_table(name) for name in jasil_orm.jasil_table_names()
    ):
        jasil_migrations.stamp(engine, BASELINE)
    jasil_migrations.upgrade(engine)


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    yield engine
    engine.dispose()


class TestBootstrapAgainstSqlite:
    def test_creates_the_tables_on_a_database_that_has_none(self, sqlite_engine):
        _bootstrap(sqlite_engine)

        present = set(sa.inspect(sqlite_engine).get_table_names())
        assert set(jasil_orm.jasil_table_names()) <= present
        assert jasil_migrations.db_revision(sqlite_engine) == jasil_migrations.head_revision()

    def test_adopts_tables_this_application_created_without_recreating_them(self, sqlite_engine):
        # The case every existing install and every fresh install hits on first
        # boot: the tables are already there and the version table is not. The
        # bootstrap must adopt them rather than fail on CREATE TABLE.
        for name in jasil_orm.jasil_table_names():
            Base.metadata.tables[name].create(sqlite_engine)
        assert jasil_migrations.db_revision(sqlite_engine) is None

        _bootstrap(sqlite_engine)

        assert jasil_migrations.db_revision(sqlite_engine) == jasil_migrations.head_revision()

    def test_is_idempotent_across_restarts(self, sqlite_engine):
        _bootstrap(sqlite_engine)
        recorded = jasil_migrations.db_revision(sqlite_engine)

        _bootstrap(sqlite_engine)

        assert jasil_migrations.db_revision(sqlite_engine) == recorded


class TestBaselineAssumptions:
    def test_baseline_is_the_substrates_base_revision(self):
        # If JASIL ever re-bases its history, stamping the old id would record a
        # revision that no longer exists, so the assumption is checked against
        # the installed release rather than held.
        config = Config()
        config.set_main_option("script_location", str(pathlib.Path(jasil_migrations.__file__).parent))

        assert ScriptDirectory.from_config(config).get_base() == BASELINE

    def test_application_history_still_creates_the_substrate_tables(self):
        # The bootstrap stamps because these revisions exist. Were they removed,
        # a fresh install would arrive with no tables and skip the stamp, which
        # is still correct but for a different reason than the one documented.
        versions = pathlib.Path("app/alembic/versions")
        sources = "\n".join(p.read_text() for p in versions.rglob("*.py"))

        for table in jasil_orm.jasil_table_names():
            assert f'create_table(\n        "{table}"' in sources or f'"{table}"' in sources
