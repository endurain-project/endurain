"""Tests for the migration that stores the OAuth state's nonce and PKCE verifier encrypted (63)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

import modules.auth.oauth_state.models as oauth_state_models

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/63_oauth_state_encrypted_secrets.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("oauth_state_encrypted_secrets", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(migration, step):
    calls = []
    with (
        patch.object(migration.op, "execute", side_effect=lambda statement: calls.append(("execute", str(statement)))),
        patch.object(migration.op, "alter_column", side_effect=lambda *a, **kw: calls.append(("alter", a, kw))),
    ):
        step()
    return calls


def test_it_has_its_revision_and_chains_onto_the_client_fingerprint_revision():
    migration = _migration_module()

    assert migration.revision == "c63e1a2b3d4f"
    assert migration.down_revision == "b62d4f8a1c75"


def test_the_upgrade_deletes_the_states_then_widens_both_columns():
    migration = _migration_module()

    delete, nonce, verifier = _run(migration, migration.upgrade)

    assert delete == ("execute", "DELETE FROM oauth_states")
    assert nonce[1] == ("oauth_states", "nonce")
    assert isinstance(nonce[2]["type_"], sa.Text) and nonce[2]["existing_nullable"] is False
    assert verifier[1] == ("oauth_states", "idp_code_verifier")
    assert isinstance(verifier[2]["type_"], sa.Text) and verifier[2]["existing_nullable"] is True


def test_the_upgrade_matches_the_model_comments():
    migration = _migration_module()
    table = oauth_state_models.OAuthState.__table__

    _, nonce, verifier = _run(migration, migration.upgrade)

    assert nonce[2]["comment"] == table.c.nonce.comment
    assert verifier[2]["comment"] == table.c.idp_code_verifier.comment
    assert isinstance(table.c.nonce.type, sa.Text) and isinstance(table.c.idp_code_verifier.type, sa.Text)


def test_the_upgrade_deletes_the_existing_states():
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE oauth_states (id VARCHAR PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO oauth_states (id) VALUES ('a'), ('b')"))
        with (
            patch.object(migration.op, "execute", side_effect=lambda statement: conn.execute(sa.text(str(statement)))),
            patch.object(migration.op, "alter_column"),
        ):
            migration.upgrade()

        assert conn.execute(sa.text("SELECT count(*) FROM oauth_states")).scalar_one() == 0
    engine.dispose()


def test_the_downgrade_deletes_the_states_then_narrows_the_columns_back():
    migration = _migration_module()

    delete, verifier, nonce = _run(migration, migration.downgrade)

    assert delete == ("execute", "DELETE FROM oauth_states")
    assert verifier[1] == ("oauth_states", "idp_code_verifier")
    assert verifier[2]["type_"].length == 128 and verifier[2]["existing_nullable"] is True
    assert nonce[1] == ("oauth_states", "nonce")
    assert nonce[2]["type_"].length == 64 and nonce[2]["existing_nullable"] is False
