"""Enabled TOTP secrets move from ``users_mfa`` to ``mfa_factors`` and back, on the real chain against PostgreSQL."""

from sqlalchemy import text

from tests._helpers import alembic_chain

_REVISION_BEFORE = "a70d3b8e5f19"
_REVISION = "a71e4c9d2b60"


def test_upgrade_moves_only_the_enabled_secrets_and_downgrade_writes_them_back(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_BEFORE)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        for user_id, enabled, secret in ((1, True, "cipher-1"), (2, False, None), (3, True, "cipher-3")):
            connection.execute(
                text("INSERT INTO users_mfa (user_id, mfa_enabled, mfa_secret) VALUES (:u, :e, :s)"),
                {"u": user_id, "e": enabled, "s": secret},
            )

    alembic_chain.upgrade(upgrade_db, _REVISION)

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

    alembic_chain.downgrade(upgrade_db, _REVISION_BEFORE)

    with upgrade_db.connect() as connection:
        restored = connection.execute(
            text("SELECT user_id, mfa_enabled, mfa_secret FROM users_mfa ORDER BY user_id")
        ).all()
        table_gone = connection.scalar(text("SELECT to_regclass('mfa_factors')")) is None
    assert [tuple(row) for row in restored] == [(1, False, None), (2, True, "c2"), (3, True, "cipher-3")]
    assert table_gone
