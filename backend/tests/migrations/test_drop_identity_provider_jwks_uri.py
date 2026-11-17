"""Tests for the migration that drops the unused ``jwks_uri`` column of an identity provider (revision 79)."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/9_sync_timestamps_and_access_checks.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("drop_identity_provider_jwks_uri", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine_with_column() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE identity_providers (id INTEGER PRIMARY KEY, slug VARCHAR(50), jwks_uri VARCHAR(500))")
        )
        connection.execute(sa.text("INSERT INTO identity_providers (slug, jwks_uri) VALUES ('a', 'https://a/jwks')"))
    return engine


def _columns(engine: sa.Engine) -> dict[str, sa.engine.interfaces.ReflectedColumn]:
    return {column["name"]: column for column in sa.inspect(engine).get_columns("identity_providers")}


def test_the_upgrade_drops_the_column_and_keeps_the_rows():
    migration = _migration_module()
    engine = _engine_with_column()

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade_drop_identity_provider_jwks_uri()

    assert set(_columns(engine)) == {"id", "slug"}
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT slug FROM identity_providers")).scalars().all() == ["a"]


def test_the_downgrade_restores_a_nullable_column():
    migration = _migration_module()
    engine = _engine_with_column()
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade_drop_identity_provider_jwks_uri()

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade_drop_identity_provider_jwks_uri()

    column = _columns(engine)["jwks_uri"]
    assert column["nullable"] is True
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT jwks_uri FROM identity_providers")).scalars().all() == [None]
