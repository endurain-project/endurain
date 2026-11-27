"""A v0.21 upgrade that fails changes nothing, and a database v0.21.0 left half-upgraded still upgrades.

The chain runs in one transaction, so a refused or failed upgrade leaves the database at v0.20.x. v0.21.0 committed
part of the chain before building two indexes, so a failure after either of those points left the schema ahead of
``alembic_version``.
"""

from contextlib import contextmanager

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_HEAD = alembic_chain.script_directory().get_current_head()
_ISSUER = "https://auth.example.com"


@contextmanager
def _failing_statement(engine, fragment: str):
    """Raise on the first statement containing ``fragment``, as a crash at that point of the upgrade would."""

    def fail(_conn, _cursor, statement, _parameters, _context, _executemany):
        if fragment in statement:
            raise RuntimeError("injected failure")

    sa.event.listen(engine, "before_cursor_execute", fail)
    try:
        yield
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail)


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def _schema(engine) -> list[tuple]:
    """Every column, index and constraint of the ``public`` schema."""
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT 'column', table_name, column_name || ' ' || data_type || ' ' || is_nullable "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "UNION ALL SELECT 'index', tablename, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "UNION ALL SELECT 'constraint', conrelid::regclass::text, conname || ' ' || pg_get_constraintdef(oid) "
                "FROM pg_constraint WHERE connamespace = 'public'::regnamespace "
                "ORDER BY 1, 2, 3"
            )
        )
        return [tuple(row) for row in rows]


def _invalid_indexes(engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.text("SELECT indexrelid::regclass::text FROM pg_index WHERE NOT indisvalid")
            ).scalars()
        )


def _seed_v0_20(engine) -> None:
    alembic_chain.upgrade(engine, alembic_chain.V0_20_HEAD)
    with engine.begin() as connection:
        alembic_chain.seed_v0_20(connection)


def _add_providers_sharing_an_issuer(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO identity_providers (id, name, slug, provider_type, enabled, auto_create_users, "
                "sync_user_info, issuer_url) VALUES (2, 'Old', 'old', 'oidc', false, false, false, :issuer), "
                "(3, 'Current', 'current', 'oidc', true, false, false, :issuer)"
            ),
            {"issuer": _ISSUER},
        )


def _delete_provider(engine, slug: str) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM identity_providers WHERE slug = :slug"), {"slug": slug})


def _assert_upgraded(engine) -> None:
    assert _version(engine) == _HEAD
    alembic_chain.bootstrap_substrate(engine)
    assert alembic_chain.schema_differences(engine) == []
    assert _invalid_indexes(engine) == []


def test_an_upgrade_refused_for_a_shared_issuer_leaves_the_v0_20_database_unchanged(upgrade_db):
    _seed_v0_20(upgrade_db)
    _add_providers_sharing_an_issuer(upgrade_db)
    schema, rows = _schema(upgrade_db), alembic_chain.row_counts(upgrade_db)

    for _attempt in range(2):
        with pytest.raises(RuntimeError, match="used by current, old"):
            alembic_chain.upgrade(upgrade_db, "head")

        assert _version(upgrade_db) == alembic_chain.V0_20_HEAD
        assert _schema(upgrade_db) == schema
        assert alembic_chain.row_counts(upgrade_db) == rows

    _delete_provider(upgrade_db, "old")
    alembic_chain.upgrade(upgrade_db, "head")

    _assert_upgraded(upgrade_db)


def test_an_upgrade_that_fails_at_its_last_statement_leaves_the_v0_20_database_unchanged(upgrade_db):
    _seed_v0_20(upgrade_db)
    schema, rows = _schema(upgrade_db), alembic_chain.row_counts(upgrade_db)

    with (
        _failing_statement(upgrade_db, f"SET version_num='{_HEAD}'"),
        pytest.raises(RuntimeError, match="injected failure"),
    ):
        alembic_chain.upgrade(upgrade_db, "head")

    assert _version(upgrade_db) == alembic_chain.V0_20_HEAD
    assert _schema(upgrade_db) == schema
    assert alembic_chain.row_counts(upgrade_db) == rows

    alembic_chain.upgrade(upgrade_db, "head")

    _assert_upgraded(upgrade_db)


#: Where v0.21.0 committed part of the chain: the revision ``alembic_version`` was left at, the revision file that
#: was running, its index step, and the indexes that step built.
_INTERRUPTIONS = {
    "revision 2": (
        "c5cfe02a11c2",
        "2_constraints_versions_and_settings.py",
        "notifications_user_created_index",
        ("ix_notifications_user_id_created_at", "ix_notifications_read_created_at"),
    ),
    "revision 8": (
        "c91ac2dad0f0",
        "8_security_generations_and_mfa.py",
        "rotated_tokens_replacement_index",
        ("ix_rotated_refresh_tokens_expires_at_with_replacement",),
    ),
}


def _leave_half_upgraded(engine, interruption: str, index_state: str) -> None:
    """Bring a seeded database to the state v0.21.0 left it in when it stopped at ``interruption``.

    Args:
        engine: The engine of the database to change.
        interruption: A key of ``_INTERRUPTIONS``.
        index_state: Whether the indexes built outside the transaction are ``missing``, ``built`` or ``invalid``,
            as a build that was stopped half way leaves them.
    """
    committed_revision, file_name, index_step, indexes = _INTERRUPTIONS[interruption]
    alembic_chain.upgrade(engine, committed_revision)
    alembic_chain.run_steps_before(engine, file_name, index_step)
    if index_state == "missing":
        return
    alembic_chain.run_step(engine, file_name, index_step)
    if index_state == "invalid":
        with engine.begin() as connection:
            for name in indexes:
                connection.execute(
                    sa.text("UPDATE pg_index SET indisvalid = false WHERE indexrelid = to_regclass(:name)"),
                    {"name": name},
                )
        assert set(_invalid_indexes(engine)) == set(indexes)


@pytest.mark.parametrize("index_state", ["missing", "built", "invalid"])
@pytest.mark.parametrize("interruption", list(_INTERRUPTIONS))
def test_a_database_v0_21_0_left_half_upgraded_upgrades_to_head(upgrade_db, interruption, index_state):
    _seed_v0_20(upgrade_db)
    _leave_half_upgraded(upgrade_db, interruption, index_state)

    alembic_chain.upgrade(upgrade_db, "head")

    _assert_upgraded(upgrade_db)


def test_a_half_upgraded_database_with_a_shared_issuer_upgrades_once_a_provider_is_deleted(upgrade_db):
    _seed_v0_20(upgrade_db)
    _add_providers_sharing_an_issuer(upgrade_db)
    _leave_half_upgraded(upgrade_db, "revision 2", "built")

    with pytest.raises(RuntimeError, match="used by current, old"):
        alembic_chain.upgrade(upgrade_db, "head")
    _delete_provider(upgrade_db, "old")
    alembic_chain.upgrade(upgrade_db, "head")

    _assert_upgraded(upgrade_db)
