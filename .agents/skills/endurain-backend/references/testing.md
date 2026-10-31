# Testing

- Tests live in `backend/tests/` mirroring `backend/app/`; files `test_*.py`, grouped in classes.
- Use fixtures from `conftest.py`.
- Unit tests of a pure function or a model definition inspect attributes (`MyModel.id.type.python_type == int`) rather than instantiating rows; tests of persistence may insert rows against a real session (see below).
- `AsyncMock` for async, `MagicMock` for sync. Patch external dependencies (providers, the network). Do not mock the session to check a query or a commit: use a real database, below.
- Cover empty/None, missing entity, errors, malformed input.
- `with pytest.raises(...) as exc_info` for exceptions.
- Async tests: `async def test_*`, check with `assert_awaited_once()`.
- Skips need `reason=`.
- CI fails under 80% total coverage; cover every branch of new code (errors, empty, refusal), not just the happy path.

```bash
uv run pytest tests/<area> -v
uv run pytest tests/<area> --cov=app/<area> --cov-report=term-missing
```

Architecture tests (boundaries, layers, logging, module template): `tests/architecture/`; role vocabulary in `tests/_helpers/module_roles.py`.

## Real-database tests

Mocks cannot show whether a change was committed, and SQLite shares one connection across sessions, so neither can show what another session sees or what a failed flush does. Use a real database for those.

| Question | Use |
| --- | --- |
| Does this query filter correctly? | `create_sqlite_session()` |
| Did the job/service commit, so a fresh session sees it? | `create_sqlite_session_factory()` and read back through a new session |
| Isolation between sessions, a failed flush, unique indexes, FKs | `tests/postgres/` (`@pytest.mark.postgres`, fixture `pg_factory`) |

- `postgres` tests need `TEST_DATABASE_URL` naming a **disposable** database (its name must contain `test`; the schema is dropped and recreated). Unset, they are skipped, so the default run needs no database.
- Persistence tests may insert rows (the "never instantiate models" rule is for unit tests); PostgreSQL enforces FKs, so create the user first with `ensure_user`.
- A test that must hold on both backends parametrizes its factory fixture over `sqlite` and `postgres` (see `test_job_state_persistence.py`).

```bash
docker run -d --rm --name endurain-test-pg -e POSTGRES_USER=endurain -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=endurain_test -p 55432:5432 postgres:18
TEST_DATABASE_URL=postgresql+psycopg://endurain:test@localhost:55432/endurain_test uv run pytest -m postgres
```
