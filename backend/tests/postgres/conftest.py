"""Fixtures for the tests that need a real PostgreSQL database.

They check behaviour SQLite cannot reproduce: per-session connection isolation,
a failed flush poisoning the session until rollback, row locks and the unique
indexes the application leans on. They run when ``TEST_DATABASE_URL`` names a
disposable database and are skipped otherwise, so the default ``pytest`` run
needs no database.

    docker run -d --rm --name endurain-test-pg -e POSTGRES_USER=endurain \\
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=endurain_test -p 55432:5432 postgres:18
    TEST_DATABASE_URL=postgresql+psycopg://endurain:test@localhost:55432/endurain_test \\
        uv run pytest -m postgres
"""

import pytest

from tests._helpers.db import (
    POSTGRES_TEST_URL_ENV,
    create_postgres_session_factory,
    drop_postgres_schema,
    postgres_test_url,
)


def pytest_collection_modifyitems(items):
    """Mark every test in this directory so ``-m postgres`` selects them."""
    for item in items:
        if "tests/postgres/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.postgres)


@pytest.fixture
def pg_factory():
    if postgres_test_url() is None:
        pytest.skip(f"{POSTGRES_TEST_URL_ENV} is not set")
    factory = create_postgres_session_factory()
    try:
        yield factory
    finally:
        drop_postgres_schema(factory)
