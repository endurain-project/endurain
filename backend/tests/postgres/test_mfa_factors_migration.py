"""Enabled TOTP secrets move from ``users_mfa`` to ``mfa_factors`` and back, on the real chain against PostgreSQL."""

from sqlalchemy import text

from tests._helpers import alembic_chain

_MIGRATION_FILE = "8_security_generations_and_mfa.py"
_MIGRATION_STEP = "mfa_factors"
_REVISION_BEFORE = "c91ac2dad0f0"


def test_upgrade_moves_only_the_enabled_secrets_and_downgrade_writes_them_back(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_BEFORE)
    alembic_chain.run_steps_before(upgrade_db, _MIGRATION_FILE, _MIGRATION_STEP)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        for user_id, enabled, secret in ((1, True, "cipher-1"), (2, False, None), (3, True, "cipher-3")):
            connection.execute(
                text("INSERT INTO users_mfa (user_id, mfa_enabled, mfa_secret) VALUES (:u, :e, :s)"),
                {"u": user_id, "e": enabled, "s": secret},
            )

    alembic_chain.run_step(upgrade_db, _MIGRATION_FILE, _MIGRATION_STEP)

    with upgrade_db.connect() as connection:
        moved = connection.execute(text("SELECT user_id, type, credential FROM mfa_factors ORDER BY user_id")).all()
        legacy_gone = connection.scalar(text("SELECT to_regclass('users_mfa')")) is None
    assert [tuple(row) for row in moved] == [(1, "totp", "cipher-1"), (3, "totp", "cipher-3")]
    assert legacy_gone

    # A user enrolled after the upgrade has a factor and no users_mfa row.
    with upgrade_db.begin() as connection:
        connection.execute(
            text("INSERT INTO mfa_factors (user_id, type, credential, created_at) VALUES (2, 'totp', 'c2', now())")
        )
        connection.execute(text("DELETE FROM mfa_factors WHERE user_id = 1"))

    alembic_chain.run_step(upgrade_db, _MIGRATION_FILE, _MIGRATION_STEP, "downgrade")

    with upgrade_db.connect() as connection:
        restored = connection.execute(
            text("SELECT user_id, mfa_enabled, mfa_secret FROM users_mfa ORDER BY user_id")
        ).all()
        table_gone = connection.scalar(text("SELECT to_regclass('mfa_factors')")) is None
    assert [tuple(row) for row in restored] == [(1, False, None), (2, True, "c2"), (3, True, "cipher-3")]
    assert table_gone
