"""The substrate schema bootstrap against a real PostgreSQL database.

Endurain's own Alembic history creates the JASIL tables in the shape of JASIL's
first revision, with no version table. The startup bootstrap has to adopt that
schema where it stands and let JASIL's own revisions bring it to head; the SQLite
variant in ``tests/migrations`` cannot see PostgreSQL's index and comment handling.
"""

import jasil.migrations as jasil_migrations
import jasil.orm as jasil_orm
import pytest
from sqlalchemy import inspect, text


def _bootstrap(engine) -> None:
    """Run the production bootstrap sequence against an arbitrary engine."""
    jasil_migrations.adopt_existing_schema(engine)
    jasil_migrations.upgrade(engine)
    jasil_migrations.verify_schema_current(engine)


def _drop_jasil_tables(engine) -> None:
    """Remove JASIL's tables under both naming schemes, and its version table."""
    with engine.begin() as connection:
        for name in jasil_orm.jasil_table_names() | jasil_orm.legacy_table_names():
            connection.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))
        connection.execute(text(f"DROP TABLE IF EXISTS {jasil_migrations.VERSION_TABLE}"))


@pytest.fixture
def engine(pg_factory):
    """The test engine, with JASIL's tables and version table removed again on teardown."""
    bound = pg_factory.kw["bind"]
    # The metadata does not declare this PostgreSQL-only index; JASIL's own
    # revisions create it, and adoption checks for it.
    with bound.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_jasil_event_log_metadata_gin "
                "ON jasil_event_log USING gin (event_metadata jsonb_path_ops)"
            )
        )
    yield bound
    _drop_jasil_tables(bound)


def _reset_to_legacy_baseline(engine) -> None:
    """Leave the unprefixed baseline tables Endurain's history created, with no version table."""
    _drop_jasil_tables(engine)
    jasil_migrations.upgrade(engine, "rev0001")
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE {jasil_migrations.VERSION_TABLE}"))


def test_a_legacy_schema_is_adopted_and_renamed_to_the_jasil_names(engine):
    _reset_to_legacy_baseline(engine)
    assert jasil_migrations.db_revision(engine) is None

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == jasil_migrations.head_revision()
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    assert jasil_orm.jasil_table_names() <= present
    assert not jasil_orm.legacy_table_names() & present
    assert "queue" in {column["name"] for column in inspector.get_columns("jasil_processing_jobs")}


def test_a_schema_already_at_head_is_adopted_unchanged(engine):
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {jasil_migrations.VERSION_TABLE}"))

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == jasil_migrations.head_revision()


def test_the_bootstrap_is_idempotent_across_restarts(engine):
    _reset_to_legacy_baseline(engine)
    _bootstrap(engine)
    recorded = jasil_migrations.db_revision(engine)

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == recorded


def test_an_incompatible_schema_is_refused_not_adopted(engine):
    _reset_to_legacy_baseline(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE processing_jobs DROP COLUMN attempts"))

    with pytest.raises(jasil_migrations.SchemaCompatibilityError):
        jasil_migrations.adopt_existing_schema(engine)
    assert jasil_migrations.db_revision(engine) is None
