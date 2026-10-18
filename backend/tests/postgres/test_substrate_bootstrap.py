"""The substrate schema bootstrap against a real PostgreSQL database.

Endurain's own Alembic history creates the JASIL tables in the shape of JASIL's
first revision, with no version table. The startup bootstrap has to adopt that
schema where it stands and let JASIL's own revisions bring it to head; the SQLite
variant in ``tests/migrations`` cannot see PostgreSQL's index and comment handling.
"""

import jasil.migrations as jasil_migrations
import pytest
from sqlalchemy import inspect, text


def _bootstrap(engine) -> None:
    """Run the production bootstrap sequence against an arbitrary engine."""
    jasil_migrations.adopt_existing_schema(engine)
    jasil_migrations.upgrade(engine)
    jasil_migrations.verify_schema_current(engine)


@pytest.fixture
def engine(pg_factory):
    """The test engine, with JASIL's version table removed again on teardown."""
    bound = pg_factory.kw["bind"]
    # The metadata does not declare this PostgreSQL-only index; Endurain's own
    # migration history creates it, and adoption checks for it.
    with bound.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_event_log_metadata_gin "
                "ON event_log USING gin (event_metadata jsonb_path_ops)"
            )
        )
    yield bound
    with bound.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS jasil_alembic_version"))


def _downgrade_to_first_revision(engine) -> None:
    """Strip what JASIL's later revisions add, leaving the shape Endurain's history creates."""
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE job_attempts"))
        connection.execute(text("DROP TABLE job_workers"))
        connection.execute(text("DROP INDEX idx_processing_jobs_queue_claim"))
        connection.execute(text("DROP INDEX idx_processing_jobs_worker_claim"))
        connection.execute(text("ALTER TABLE processing_jobs DROP COLUMN queue"))
        connection.execute(text("DROP TABLE IF EXISTS jasil_alembic_version"))


def test_a_schema_one_revision_behind_is_adopted_and_upgraded(engine):
    _downgrade_to_first_revision(engine)
    assert jasil_migrations.db_revision(engine) is None

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == jasil_migrations.head_revision()
    inspector = inspect(engine)
    assert {"job_workers", "job_attempts"} <= set(inspector.get_table_names())
    assert "queue" in {column["name"] for column in inspector.get_columns("processing_jobs")}


def test_a_schema_already_at_head_is_adopted_unchanged(engine):
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS jasil_alembic_version"))

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == jasil_migrations.head_revision()


def test_the_bootstrap_is_idempotent_across_restarts(engine):
    _downgrade_to_first_revision(engine)
    _bootstrap(engine)
    recorded = jasil_migrations.db_revision(engine)

    _bootstrap(engine)

    assert jasil_migrations.db_revision(engine) == recorded


def test_an_incompatible_schema_is_refused_not_adopted(engine):
    _downgrade_to_first_revision(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE processing_jobs DROP COLUMN attempts"))

    with pytest.raises(jasil_migrations.SchemaCompatibilityError):
        jasil_migrations.adopt_existing_schema(engine)
    assert jasil_migrations.db_revision(engine) is None
