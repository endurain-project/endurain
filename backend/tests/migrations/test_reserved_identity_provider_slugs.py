"""Tests for the migration that refuses the upgrade while a provider uses a reserved slug (revision 80)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/80_reserved_identity_provider_slugs.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("reserved_identity_provider_slugs", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(slugs: list[str]) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE identity_providers (id INTEGER PRIMARY KEY, slug VARCHAR(50) NOT NULL)"))
        for slug in slugs:
            conn.execute(sa.text("INSERT INTO identity_providers (slug) VALUES (:slug)"), {"slug": slug})
        with Operations.context(MigrationContext.configure(conn)):
            _migration_module().upgrade()


def test_the_revision_follows_migration_79():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("d80f4b6c2e93", "c79e3a5d1b82")


def test_the_upgrade_passes_when_no_provider_uses_a_reserved_slug():
    _upgrade(["google", "login-sso", "my-callback"])


def test_the_upgrade_passes_without_providers():
    _upgrade([])


def test_the_upgrade_names_every_provider_that_uses_a_reserved_slug():
    with pytest.raises(RuntimeError) as error:
        _upgrade(["google", "login", "icon"])
    message = str(error.value)
    assert "Providers using one: icon, login." in message
    assert "google" not in message
    assert "Change the slug" in message
