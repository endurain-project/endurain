"""Tests for the migration that adds the provider session id to ``idp_session_tokens`` (revision 60)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/60_idp_session_token_sid.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("idp_session_token_sid", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_provider_type_revision():
    migration = _migration_module()

    assert (migration.revision, migration.down_revision) == ("c09e5b7d2f14", "b12d4f6a8e30")


def test_the_upgrade_adds_a_nullable_bounded_column_so_existing_sign_ins_hold_no_sid():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column, patch.object(migration.op, "create_index"):
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("idp_session_tokens", "idp_sid", True)
    assert isinstance(column.type, sa.String)
    assert column.type.length == 255


def test_the_upgrade_indexes_the_lookup_by_provider_and_sid():
    migration = _migration_module()
    with patch.object(migration.op, "add_column"), patch.object(migration.op, "create_index") as create_index:
        migration.upgrade()

    create_index.assert_called_once_with(
        "ix_idp_session_tokens_idp_id_idp_sid", "idp_session_tokens", ["idp_id", "idp_sid"], unique=False
    )


def test_the_downgrade_drops_the_index_then_the_column():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_index") as drop_index,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.downgrade()

    drop_index.assert_called_once_with("ix_idp_session_tokens_idp_id_idp_sid", table_name="idp_session_tokens")
    drop_column.assert_called_once_with("idp_session_tokens", "idp_sid")


def test_the_model_declares_the_same_column_and_index():
    import modules.auth.identity_provider_links.models as identity_link_models

    table = identity_link_models.IdpSessionToken.__table__
    column = table.c.idp_sid
    assert (column.nullable, column.type.length) == (True, 255)
    indexes = {index.name: [c.name for c in index.columns] for index in table.indexes}
    assert indexes["ix_idp_session_tokens_idp_id_idp_sid"] == ["idp_id", "idp_sid"]
