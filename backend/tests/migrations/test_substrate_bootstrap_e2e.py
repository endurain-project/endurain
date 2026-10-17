"""End-to-end check of the substrate schema bootstrap against a real database.

The unit tests assert the call sequence. These run it, so a baseline that does
not match the schema this application's own history creates would fail here
rather than on a production boot.
"""

import jasil.migrations as jasil_migrations
import jasil.orm as jasil_orm
import pytest
import sqlalchemy as sa

from core.database import Base


def _bootstrap(engine) -> None:
    """Run the production bootstrap sequence against an arbitrary engine."""
    jasil_migrations.adopt_existing_schema(engine)
    jasil_migrations.upgrade(engine)
    jasil_migrations.verify_schema_current(engine)


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


class TestMigrationOwnership:
    def test_application_history_still_creates_the_substrate_tables(self):
        """Legacy Endurain revisions remain available to existing installations."""
        from pathlib import Path

        versions = Path("app/alembic/versions")
        sources = "\n".join(p.read_text() for p in versions.rglob("*.py"))

        for table in jasil_orm.jasil_table_names():
            assert f'create_table(\n        "{table}"' in sources or f'"{table}"' in sources
