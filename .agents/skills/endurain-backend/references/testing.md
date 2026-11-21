# Testing

Tests live in `backend/tests/` mirroring `backend/app/`; files are `test_*.py`.
A test asserts an outcome (rows read back, response status, headers and body, audit rows), never the calls the code made to its own collaborators.

## Pick the fixture by what the test proves

| The test proves | Use |
| --- | --- |
| A pure function, a parser, our own schema rule | No fixture, no mocks |
| A query, a constraint, in-process crud or service work | `db` (rolled back after the test) |
| What survives a failure, a refusal and its audit row, isolation, locks, races, work on another thread | `committed_sessions` |
| An HTTP route: status, headers, body, auth, scopes, ownership, `ETag`/`If-Match` | `client`, `sign_in` (built on `committed_sessions`) |
| The Alembic chain | `upgrade_db` (an empty database) |

- `db` binds the app's `SessionLocal` to one rolled-back transaction, so a rollback also discards what another session committed meanwhile; production keeps it.
- `committed_sessions` gives real commits on separate connections; the worker database is cloned again from the template afterwards.
- The `app` behind `client` is `main.create_app()`: real middleware, `/api/v1` routes, auth chain and scope checks, with no dependency overrides.
- Real-database tests run with the real security generations and audit writes on, and the platform clock starts at the current time.
- The `app` registers no event subscribers, so a request's events reach nobody; a test of a subscriber's effect registers that module's (`<module>.subscribers.register_bus_subscribers(jasil.runtime.get_active_platform().events)`).

## Writing them

- Build rows with the factories in `tests/_factories/` (`make_user`, `make_admin`, …); add a factory for a new aggregate there, staging through the module's real create path.
- With `committed_sessions`, arrange in a session you commit, act, then read the outcome back in a new session.
- Sign in with the `sign_in` fixture; never override `get_principal`, `check_scopes`, `authenticate` or `get_db`.
- Mock only what we do not own: provider APIs (Strava, Garmin, OIDC), SMTP, third-party HTTP; control time through the platform clock, never `sleep()`.
- Never assert on generated SQL text, a mocked session or `assert_called*` of our own code.
- Cover the empty, missing, malformed, refused and other-user cases, not just the happy path.
- An HTTP test of a route that names a resource checks that another user gets `404` and the owner's row is unchanged.
- Assert audit rows on the database (`jasil.audit.models.AuditLog`); `jasil.testing.capture_audit` lists rows at staging, including rolled-back ones.
- `with pytest.raises(...) as exc_info` for exceptions; skips need `reason=`.
- Tests are order-independent and parallel-safe: no random values in parametrize ids, no shared module state.
- A test that waits for another session to block polls `pg_stat_activity` on an AUTOCOMMIT connection or ends its transaction per poll: PostgreSQL snapshots that view once per transaction.

## Database

- Every run needs PostgreSQL; a test that needs it fails, never skips, when there is none.
- Without `TEST_DATABASE_URL` the run starts a throwaway `postgres:18` container (Docker must run).
- With it, it names a disposable maintenance database whose name contains `test`; the run creates `<name>_template` and one `<name>_<worker>` clone per xdist worker beside it, and drops them at the end.

## Commands

```bash
uv run pytest tests/<area> -q                 # one area, Docker starts the database
uv run pytest tests/<area> -q -n auto         # in parallel
uv run hatch run test                         # what CI runs: whole suite, parallel, branch coverage gate
docker run -d --rm --name endurain-test-pg -e POSTGRES_USER=endurain -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=endurain_test -p 55432:5432 postgres:18
TEST_DATABASE_URL=postgresql+psycopg://endurain:test@localhost:55432/endurain_test uv run pytest tests/<area> -q
```

Keep a database running and set `TEST_DATABASE_URL` to skip the container start on every run.
Architecture tests (boundaries, layers, logging, module template) are in `tests/architecture/`; the role vocabulary is in `tests/_helpers/module_roles.py`.
CI fails under 80% total branch coverage; cover every branch of new code (errors, empty, refusal).
