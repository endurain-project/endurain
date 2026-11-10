"""Enabled TOTP secrets move from ``users_mfa`` to ``mfa_factors`` and back, against real PostgreSQL."""

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from tests._helpers.db import ensure_user

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/71_mfa_factors.py"


def _migration():
    spec = importlib.util.spec_from_file_location("mfa_factors_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, migration, direction):
    with Operations.context(MigrationContext.configure(db.connection())):
        getattr(migration, direction)()
    db.commit()


def _legacy_state(db):
    """Put the MFA tables back to their shape before the migration, with two enabled users and one disabled."""
    db.execute(text("DROP TABLE mfa_factors"))
    db.execute(
        text(
            "CREATE TABLE users_mfa (id serial PRIMARY KEY, user_id integer NOT NULL UNIQUE "
            "REFERENCES users(id) ON DELETE CASCADE, mfa_enabled boolean NOT NULL DEFAULT false, "
            "mfa_secret varchar(512))"
        )
    )
    for user_id, enabled, secret in ((1, True, "cipher-1"), (2, False, None), (3, True, "cipher-3")):
        db.execute(
            text("INSERT INTO users_mfa (user_id, mfa_enabled, mfa_secret) VALUES (:u, :e, :s)"),
            {"u": user_id, "e": enabled, "s": secret},
        )
    db.commit()


def test_upgrade_moves_only_the_enabled_secrets_and_downgrade_writes_them_back(pg_factory):
    for user_id in (1, 2, 3, 4):
        ensure_user(pg_factory, user_id)
    with pg_factory() as db:
        _legacy_state(db)
        migration = _migration()

        _run(db, migration, "upgrade")
        moved = db.execute(text("SELECT user_id, type, credential FROM mfa_factors ORDER BY user_id")).all()
        legacy_gone = db.scalar(text("SELECT to_regclass('users_mfa')")) is None
        # A user enrolled after the upgrade has a factor and no users_mfa row.
        db.execute(
            text("INSERT INTO mfa_factors (user_id, type, credential, created_at) VALUES (4, 'totp', 'c4', now())")
        )
        db.execute(text("DELETE FROM mfa_factors WHERE user_id = 1"))
        db.commit()
        _run(db, migration, "downgrade")
        restored = db.execute(text("SELECT user_id, mfa_enabled, mfa_secret FROM users_mfa ORDER BY user_id")).all()
        table_gone = db.scalar(text("SELECT to_regclass('mfa_factors')")) is None
        # The table is not in the metadata, so the fixture's teardown does not know to drop it.
        db.execute(text("DROP TABLE users_mfa"))
        db.commit()

    assert [tuple(row) for row in moved] == [(1, "totp", "cipher-1"), (3, "totp", "cipher-3")]
    assert legacy_gone
    assert [tuple(row) for row in restored] == [
        (1, False, None),
        (2, False, None),
        (3, True, "cipher-3"),
        (4, True, "c4"),
    ]
    assert table_gone
