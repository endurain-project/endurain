"""Tests for the migration that settles ``provider_type`` and adds ``link_by_email`` and ``sync_email`` (revision 57)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/57_idp_provider_type_link_and_sync_flags.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("idp_provider_type_link_and_sync_flags", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE identity_providers (id INTEGER PRIMARY KEY, provider_type VARCHAR(50) NOT NULL, "
                "sync_user_info BOOLEAN NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO identity_providers (id, provider_type, sync_user_info) VALUES "
                "(1, 'oidc', 1), (2, 'saml', 0), (3, 'oauth2', 1)"
            )
        )
        yield conn
    engine.dispose()


def _upgrade(connection):
    migration = _migration_module()

    def add_column(table, column):
        default = "0" if column.server_default is not None else "NULL"
        connection.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column.name} BOOLEAN NOT NULL DEFAULT {default}"))

    with (
        patch.object(migration.op, "add_column", side_effect=add_column),
        patch.object(migration.op, "alter_column"),
        patch.object(
            migration.op, "execute", side_effect=lambda statement: connection.execute(sa.text(str(statement)))
        ),
    ):
        migration.upgrade()


def test_it_chains_onto_the_id_token_revision():
    assert _migration_module().down_revision == "d4b8f2a61c93"


def test_the_upgrade_adds_both_flags_as_non_null_columns_that_default_to_false():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "alter_column"),
        patch.object(migration.op, "execute"),
    ):
        migration.upgrade()

    columns = {call.args[1].name: call.args[1] for call in add_column.call_args_list}
    assert set(columns) == {"link_by_email", "sync_email"}
    for column in columns.values():
        assert column.nullable is False
        assert str(column.server_default.arg) == "false"


def test_a_saml_row_becomes_oauth2_and_the_others_keep_their_type(connection):
    _upgrade(connection)

    types = dict(connection.execute(sa.text("SELECT id, provider_type FROM identity_providers")).all())
    assert types == {1: "oidc", 2: "oauth2", 3: "oauth2"}


def test_existing_providers_keep_linking_by_email(connection):
    _upgrade(connection)

    flags = connection.execute(sa.text("SELECT link_by_email FROM identity_providers")).scalars().all()
    assert all(flag == 1 for flag in flags)


def test_existing_providers_keep_the_email_sync_they_had(connection):
    _upgrade(connection)

    synced = dict(connection.execute(sa.text("SELECT id, sync_email FROM identity_providers")).all())
    assert synced == {1: 1, 2: 0, 3: 1}


def test_the_downgrade_drops_both_flags_and_leaves_the_provider_types():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_column") as drop_column,
        patch.object(migration.op, "alter_column"),
        patch.object(migration.op, "execute") as execute,
    ):
        migration.downgrade()

    assert [call.args for call in drop_column.call_args_list] == [
        ("identity_providers", "sync_email"),
        ("identity_providers", "link_by_email"),
    ]
    execute.assert_not_called()
