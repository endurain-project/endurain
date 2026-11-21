"""The PostgreSQL databases the test run works in.

``TEST_DATABASE_URL`` names a disposable *maintenance* database (its name must contain ``test``). When it is unset, the
run starts a throwaway PostgreSQL container and points the variable at it. Beside the maintenance database the harness
creates, and only ever drops, databases whose names it derives from it:

- ``<name>_template``: migrated once per run with the application's Alembic chain and the substrate upgrade, by
  whichever process needs it first, under an advisory lock on the maintenance database. It holds the rows the
  migrations seed and nothing else.
- ``<name>_<worker>``: the database of one pytest-xdist worker (``main`` without xdist), cloned from the template.
  The application's own engine points at it, because :func:`bootstrap` sets the ``DB_*`` variables before
  ``core.database`` is imported.
- ``<name>_<worker>_chain``: an empty database per worker for the tests that run the Alembic chain themselves.

This module is imported by the root ``conftest.py`` before any application module, so it imports nothing from the
application at module level.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

import sqlalchemy as sa
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

#: Environment variable naming the disposable maintenance database.
TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"

#: Identifies one test run, so a template left by an earlier run is rebuilt rather than reused.
_RUN_ID_ENV = "ENDURAIN_TEST_RUN_ID"

#: Set when no database could be provided; the database fixtures fail with it.
_UNAVAILABLE_ENV = "ENDURAIN_TEST_DATABASE_UNAVAILABLE"

#: The image the run starts when ``TEST_DATABASE_URL`` is unset: the major version CI and the compose file run.
_CONTAINER_IMAGE = "postgres:18"
#: Server settings of a disposable database: nothing it writes needs to survive a crash.
_NO_DURABILITY = "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"

#: Arbitrary constant naming the harness's advisory lock on the maintenance database.
_LOCK_KEY = 7_203_419_777

#: The session options the application's engine uses, so the template is migrated as production migrates.
_CONNECT_ARGS = {"options": "-c timezone=utc"}

#: PostgreSQL's limit on an identifier, which a database name is.
_MAX_IDENTIFIER_LENGTH = 63

_container = None


def worker_id() -> str:
    """Return the pytest-xdist worker this process is (``gw0``, ``gw1``, …), or ``main`` without xdist."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


def _is_worker() -> bool:
    return "PYTEST_XDIST_WORKER" in os.environ


def is_available() -> bool:
    """Return whether the run has a test database."""
    return not os.environ.get(_UNAVAILABLE_ENV) and bool(os.environ.get(TEST_DATABASE_URL_ENV))


def maintenance_url() -> URL:
    """Return the maintenance database's URL after checking that it is disposable.

    Raises:
        RuntimeError: When no database is available or its name does not contain ``test``.
    """
    unavailable = os.environ.get(_UNAVAILABLE_ENV)
    if unavailable:
        raise RuntimeError(unavailable)
    raw = os.environ.get(TEST_DATABASE_URL_ENV)
    if not raw:
        raise RuntimeError(f"{TEST_DATABASE_URL_ENV} is not set")
    url = make_url(raw)
    if "test" not in (url.database or ""):
        raise RuntimeError(
            f"Refusing to use '{url.database}': {TEST_DATABASE_URL_ENV} must name a disposable database whose name "
            "contains 'test'."
        )
    return url


def _derived_name(suffix: str) -> str:
    name = f"{maintenance_url().database}_{suffix}"
    if len(name) > _MAX_IDENTIFIER_LENGTH:
        raise RuntimeError(f"The test database name '{name}' is longer than PostgreSQL allows.")
    return name


def template_database() -> str:
    """Return the name of the migrated template every worker database is cloned from."""
    return _derived_name("template")


def worker_database() -> str:
    """Return the name of this process's database."""
    return _derived_name(worker_id())


def chain_database() -> str:
    """Return the name of this process's empty database for the Alembic chain tests."""
    return _derived_name(f"{worker_id()}_chain")


def database_url(database: str) -> URL:
    """Return the URL of a database on the test server."""
    return maintenance_url().set(database=database)


def database_engine(database: str) -> Engine:
    """Create an engine on a database of the test server with the application's session options.

    The caller disposes it.
    """
    return sa.create_engine(database_url(database), connect_args=_CONNECT_ARGS)


def _start_container() -> str:
    """Start a throwaway PostgreSQL container and return the URL of its maintenance database."""
    global _container
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer(_CONTAINER_IMAGE, username="endurain", password="test", dbname="endurain_test")
    # The data is thrown away with the container, so it is not flushed to disk: a clone of the template per test is
    # then several times faster.
    container.with_command(_NO_DURABILITY)
    container.start()
    _container = container
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return URL.create(
        "postgresql+psycopg", username="endurain", password="test", host=host, port=int(port), database="endurain_test"
    ).render_as_string(hide_password=False)


def bootstrap() -> None:
    """Point the application's database settings at this process's test database.

    Called by the root ``conftest.py`` before any application module is imported. The controller process starts a
    container when ``TEST_DATABASE_URL`` is unset and publishes its URL, which the xdist workers it spawns inherit. When
    no database can be provided, the failure is recorded instead of raised, so a run of tests that need no database
    still works and every test that needs one fails with the reason.
    """
    os.environ.setdefault(_RUN_ID_ENV, uuid.uuid4().hex)
    if not os.environ.get(TEST_DATABASE_URL_ENV) and not _is_worker():
        try:
            os.environ[TEST_DATABASE_URL_ENV] = _start_container()
        except Exception as err:
            os.environ[_UNAVAILABLE_ENV] = (
                f"No test database: {TEST_DATABASE_URL_ENV} is unset and a PostgreSQL container could not be started "
                f"({type(err).__name__}: {err}). Start Docker, or set {TEST_DATABASE_URL_ENV} to a disposable "
                "database whose name contains 'test'."
            )
            return
    try:
        url = database_url(worker_database())
    except RuntimeError as err:
        os.environ[_UNAVAILABLE_ENV] = str(err)
        return
    os.environ.update(
        {
            "DB_HOST": url.host or "localhost",
            "DB_PORT": str(url.port or 5432),
            "DB_USER": url.username or "",
            "DB_PASSWORD": url.password or "",
            "DB_DATABASE": url.database or "",
        }
    )
    # A password file would win over the variable set above.
    os.environ.pop("DB_PASSWORD_FILE", None)


def stop_container() -> None:
    """Stop the container :func:`bootstrap` started, if it started one."""
    global _container
    if _container is not None:
        _container.stop()
        _container = None


def _quote(connection: Connection, name: str) -> str:
    return connection.dialect.identifier_preparer.quote_identifier(name)


@cache
def _maintenance_engine() -> Engine:
    """The process's autocommit engine on the maintenance database, where databases are created and dropped."""
    return sa.create_engine(maintenance_url(), isolation_level="AUTOCOMMIT")


@contextmanager
def _maintenance_connection() -> Iterator[Connection]:
    with _maintenance_engine().connect() as connection:
        yield connection


@contextmanager
def _template_lock(connection: Connection) -> Iterator[None]:
    """Hold the harness's advisory lock, so one process builds the template while the others wait for it."""
    connection.execute(sa.text("SELECT pg_advisory_lock(:key)"), {"key": _LOCK_KEY})
    try:
        yield
    finally:
        connection.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})


def _drop(connection: Connection, name: str) -> None:
    connection.execute(sa.text(f"DROP DATABASE IF EXISTS {_quote(connection, name)} WITH (FORCE)"))


def _template_run_id(connection: Connection, name: str) -> str | None:
    return connection.execute(
        sa.text("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = :name"), {"name": name}
    ).scalar_one_or_none()


def _build_template(connection: Connection, name: str, run_id: str) -> None:
    """Create the template and bring it to the schema application startup produces."""
    from tests._helpers import alembic_chain

    _drop(connection, name)
    connection.execute(sa.text(f"CREATE DATABASE {_quote(connection, name)}"))
    engine = database_engine(name)
    try:
        alembic_chain.upgrade(engine, "head")
        alembic_chain.bootstrap_substrate(engine)
    finally:
        engine.dispose()
    connection.execute(sa.text(f"COMMENT ON DATABASE {_quote(connection, name)} IS {_literal(run_id)}"))


def _literal(value: str) -> str:
    if not value.isalnum():
        raise ValueError("A run id is alphanumeric.")
    return f"'{value}'"


def _clone(connection: Connection, template: str, name: str) -> None:
    """Replace a database with a copy of the template; copies from one template may run side by side."""
    _drop(connection, name)
    connection.execute(sa.text(f"CREATE DATABASE {_quote(connection, name)} TEMPLATE {_quote(connection, template)}"))


def create_worker_database() -> None:
    """Clone this process's database from the template, building the template first when this run has none."""
    run_id = os.environ[_RUN_ID_ENV]
    template = template_database()
    with _maintenance_connection() as connection:
        with _template_lock(connection):
            if _template_run_id(connection, template) != run_id:
                _build_template(connection, template, run_id)
        _clone(connection, template, worker_database())


def reset_worker_database(app_engine: Engine) -> None:
    """Return this process's database to the template's state.

    Closes the application's pooled connections first: a database cannot be cloned over while connections to it are
    open, and ``WITH (FORCE)`` would end any a test left behind.

    Args:
        app_engine: The application's engine, whose pool holds connections to the worker database.
    """
    app_engine.dispose()
    with _maintenance_connection() as connection:
        _clone(connection, template_database(), worker_database())


def create_chain_database() -> Engine:
    """Create this process's empty chain database and return an engine on it; the caller disposes it."""
    with _maintenance_connection() as connection:
        _drop(connection, chain_database())
        connection.execute(sa.text(f"CREATE DATABASE {_quote(connection, chain_database())}"))
    return database_engine(chain_database())


def drop_process_databases() -> None:
    """Drop the databases this process created: its own and its chain database."""
    with _maintenance_connection() as connection:
        _drop(connection, worker_database())
        _drop(connection, chain_database())


def drop_template() -> None:
    """Drop the template, once no worker needs it any more."""
    with _maintenance_connection() as connection:
        _drop(connection, template_database())
    _maintenance_engine().dispose()


@contextmanager
def rolled_back_session(engine: Engine, factory: sessionmaker[Session]) -> Iterator[Session]:
    """Bind the application's session factory to one connection whose transaction is rolled back at the end.

    Every session the factory opens meanwhile joins that transaction through a savepoint, so a ``commit()`` ends only
    its savepoint. Sessions must end in the reverse order they first ran a statement in, as nested work does; ending
    an outer one first fails with ``InvalidSavepointSpecification`` rather than passing silently.

    Args:
        engine: The application's engine.
        factory: The application's session factory, bound back to ``engine`` afterwards.

    Yields:
        A session of the factory inside that transaction.
    """
    connection = engine.connect()
    outer = connection.begin()
    original = dict(factory.kw)
    factory.configure(bind=connection, join_transaction_mode="create_savepoint")
    session = factory()
    try:
        yield session
    finally:
        session.close()
        factory.kw.clear()
        factory.kw.update(original)
        outer.rollback()
        connection.close()
