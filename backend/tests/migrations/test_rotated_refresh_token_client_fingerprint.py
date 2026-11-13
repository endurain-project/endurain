"""Tests for the migration that binds rotated refresh tokens to the rotating client (62)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

import modules.auth.rotated_refresh_tokens.models as rotated_token_models

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/62_rotated_refresh_token_client_fingerprint.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("rotated_refresh_token_client_fingerprint", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_has_its_revision_and_chains_onto_the_issuer_unique_revision():
    migration = _migration_module()

    assert migration.revision == "b62d4f8a1c75"
    assert migration.down_revision == "e61b7c3d9a40"


def test_the_upgrade_deletes_the_rotated_records_then_adds_the_non_null_fingerprint():
    migration = _migration_module()
    calls = []
    with (
        patch.object(migration.op, "execute", side_effect=lambda statement: calls.append(("execute", str(statement)))),
        patch.object(migration.op, "add_column", side_effect=lambda table, column: calls.append((table, column))),
    ):
        migration.upgrade()

    (_, delete), (table, column) = calls
    assert delete == "DELETE FROM rotated_refresh_tokens"
    assert table == "rotated_refresh_tokens"
    assert (column.name, column.nullable, column.server_default) == ("client_fingerprint", False, None)
    assert isinstance(column.type, sa.String) and column.type.length == 64


def test_the_upgrade_deletes_the_existing_rotated_records():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE rotated_refresh_tokens (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO rotated_refresh_tokens (id) VALUES (1), (2)"))
        with (
            patch.object(migration.op, "execute", side_effect=lambda statement: conn.execute(sa.text(str(statement)))),
            patch.object(migration.op, "add_column"),
        ):
            migration.upgrade()

        assert conn.execute(sa.text("SELECT count(*) FROM rotated_refresh_tokens")).scalar_one() == 0
    engine.dispose()


def test_the_column_matches_the_model():
    migration = _migration_module()
    with patch.object(migration.op, "execute"), patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()
    column = add_column.call_args.args[1]
    model_column = rotated_token_models.RotatedRefreshToken.__table__.c.client_fingerprint

    assert (column.nullable, column.type.length, column.comment) == (
        model_column.nullable,
        model_column.type.length,
        model_column.comment,
    )


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("rotated_refresh_tokens", "client_fingerprint")
