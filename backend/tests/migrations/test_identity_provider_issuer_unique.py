"""Tests for the migration that makes an identity provider's issuer unique (revision 61)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/61_identity_provider_issuer_unique.py"
)
_INDEX = "uq_identity_providers_issuer_url_normalized"


def _migration_module():
    spec = importlib.util.spec_from_file_location("identity_provider_issuer_unique", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine_with(rows: list[tuple[str, str | None]]) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE identity_providers (id INTEGER PRIMARY KEY, slug VARCHAR(50), issuer_url VARCHAR(500))"
            )
        )
        for slug, issuer in rows:
            connection.execute(
                sa.text("INSERT INTO identity_providers (slug, issuer_url) VALUES (:slug, :issuer)"),
                {"slug": slug, "issuer": issuer},
            )
    return engine


def _index_names(engine: sa.Engine) -> list[str]:
    """List the table's indexes from ``sqlite_master``; reflection skips expression indexes."""
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'identity_providers'")
            ).scalars()
        )


def test_it_chains_onto_the_session_id_revision():
    migration = _migration_module()

    assert (migration.revision, migration.down_revision) == ("e61b7c3d9a40", "c09e5b7d2f14")


def test_the_upgrade_creates_the_unique_index_and_the_downgrade_drops_it():
    migration = _migration_module()
    engine = _engine_with([("a", "https://a.example.com"), ("b", None), ("c", None)])
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    assert _index_names(engine) == [_INDEX]
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
    assert _index_names(engine) == []


def test_the_index_refuses_an_issuer_that_differs_only_by_trailing_slashes_but_not_two_missing_issuers():
    migration = _migration_module()
    engine = _engine_with([("b", None), ("c", None), ("a", "https://a.example.com/")])
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO identity_providers (slug, issuer_url) VALUES ('d', 'https://a.example.com//')")
        )


def test_the_upgrade_refuses_and_names_the_providers_that_share_an_issuer():
    migration = _migration_module()
    engine = _engine_with(
        [("one", "https://a.example.com/"), ("two", "https://a.example.com"), ("solo", "https://b.example.com")]
    )
    with (
        engine.begin() as connection,
        Operations.context(MigrationContext.configure(connection)),
        pytest.raises(RuntimeError) as raised,
    ):
        migration.upgrade()

    message = str(raised.value)
    assert "https://a.example.com is used by one, two" in message
    assert "solo" not in message
    assert _index_names(engine) == []
