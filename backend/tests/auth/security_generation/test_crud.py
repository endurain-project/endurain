"""Tests for the staged persistence of account security generations."""

import uuid

from sqlalchemy.dialects import postgresql

import modules.auth.security_generation.crud as security_generation_crud

USER = uuid.uuid4()


def _sql(statement) -> str:
    """Render a statement for PostgreSQL, with its parameters inlined."""
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_read_selects_without_writing_or_locking(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = 4

    assert security_generation_crud.read(USER, mock_db) == 4

    sql = _sql(mock_db.execute.call_args.args[0])
    assert sql.startswith("SELECT account_security_generations.generation")
    assert "FOR UPDATE" not in sql
    mock_db.execute.assert_called_once()
    mock_db.flush.assert_not_called()


def test_read_is_zero_without_a_row(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    assert security_generation_crud.read(USER, mock_db) == 0


def test_bump_upserts_adding_one_and_flushes(mock_db):
    security_generation_crud.bump(USER, mock_db)

    sql = _sql(mock_db.execute.call_args.args[0])
    assert f"VALUES ('{USER}', 1)" in sql
    assert "ON CONFLICT (user_id) DO UPDATE SET generation = (account_security_generations.generation + 1)" in sql
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_lock_creates_a_missing_row_at_zero_then_selects_it_for_update(mock_db):
    mock_db.execute.return_value.scalar_one.return_value = 7

    assert security_generation_crud.lock(USER, mock_db) == 7

    insert_sql = _sql(mock_db.execute.call_args_list[0].args[0])
    assert "INSERT INTO account_security_generations" in insert_sql
    assert f"VALUES ('{USER}', 0)" in insert_sql
    assert "ON CONFLICT (user_id) DO NOTHING" in insert_sql
    assert _sql(mock_db.execute.call_args_list[1].args[0]).endswith("FOR UPDATE")
    mock_db.commit.assert_not_called()
