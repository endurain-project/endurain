"""Database engine, session factory, and declarative base."""

import os
from collections.abc import Callable, Generator, Mapping
from datetime import datetime

import jasil.orm as jasil_orm
from sqlalchemy import DateTime, create_engine, func, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

import core.config as core_config
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# Resolve and validate the database password before
# building the connection URL so the failure mode is a
# clear startup error instead of a confusing connection
# refusal later.
_db_password = core_config.read_secret("DB_PASSWORD")
if not _db_password:
    raise RuntimeError("DB_PASSWORD is not configured. Set DB_PASSWORD or DB_PASSWORD_FILE environment variable.")

# Define the database connection URL using environment variables
db_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ.get("DB_USER", "endurain"),
    password=_db_password,
    host=os.environ.get("DB_HOST", "postgres"),
    port=int(os.environ.get("DB_PORT", "5432")),
    database=os.environ.get("DB_DATABASE", "endurain"),
)

#: Connections the pool keeps open, and extra ones it may open under load, per process.
_DEFAULT_POOL_SIZE = 20
_DEFAULT_MAX_OVERFLOW = 40

# A row lock held by a stuck transaction fails the waiting statement after
# _LOCK_TIMEOUT_SECONDS instead of parking a request thread (and its pooled connection)
# for as long as the holder lives.
_LOCK_TIMEOUT_SECONDS = 30

#: Rows a maintenance purge deletes per transaction, so it never holds a long lock.
PURGE_BATCH_SIZE = 1000


def _int_env(env: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    """Read an integer setting from the environment, tolerating a missing or unusable value.

    Args:
        env: The environment to read.
        name: The variable to read.
        default: The value used when the variable is unset, empty, not an integer or below ``minimum``.
        minimum: The lowest accepted value.

    Returns:
        The configured value, or ``default``.
    """
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = minimum - 1
    if value < minimum:
        logger.warning(
            "Invalid %s value, expected an integer of at least %d; using %d",
            name,
            minimum,
            default,
            extra=core_logger.context(console=True),
        )
        return default
    return value


def _pool_options(env: Mapping[str, str]) -> dict[str, int]:
    """Build the connection pool sizing from ``DB_POOL_SIZE`` and ``DB_MAX_OVERFLOW``.

    Args:
        env: The environment to read.

    Returns:
        The ``pool_size`` and ``max_overflow`` engine arguments.
    """
    return {
        "pool_size": _int_env(env, "DB_POOL_SIZE", _DEFAULT_POOL_SIZE, minimum=1),
        "max_overflow": _int_env(env, "DB_MAX_OVERFLOW", _DEFAULT_MAX_OVERFLOW, minimum=0),
    }


def _connect_args(env: Mapping[str, str]) -> dict:
    """Build the connection arguments.

    Pins the session timezone to UTC. The import parsers emit naive UTC wall-clock timestamps and
    the datetime columns are TIMESTAMP WITH TIME ZONE, so without this PostgreSQL would read naive
    values in the server's session timezone and shift stored instants when TZ != UTC. Bounds how
    long a statement may wait for a row lock. ``DB_STATEMENT_TIMEOUT_SECONDS`` bounds how long a
    statement may run (off at 0, the default), so a runaway query cannot hold a request thread and
    its pooled connection indefinitely. ``DB_SSLMODE`` opts into TLS (OWASP A02), with libpq values:
    disable | allow | prefer | require | verify-ca | verify-full.

    Args:
        env: The environment to read.

    Returns:
        The ``connect_args`` engine argument.
    """
    options = f"-c timezone=utc -c lock_timeout={_LOCK_TIMEOUT_SECONDS}s"
    statement_timeout = _int_env(env, "DB_STATEMENT_TIMEOUT_SECONDS", 0, minimum=0)
    if statement_timeout:
        options += f" -c statement_timeout={statement_timeout}s"
    connect_args: dict = {"options": options}
    sslmode = env.get("DB_SSLMODE", "").strip().lower()
    if sslmode:
        connect_args["sslmode"] = sslmode
    return connect_args


# Create the SQLAlchemy engine.
# Pool budget: pool_size + max_overflow connections per process (60 by default). The total is
# that times every web worker, replica and dedicated worker, and must stay below PostgreSQL
# max_connections (default 100). Lower DB_POOL_SIZE / DB_MAX_OVERFLOW, or front the database
# with PgBouncer in session pooling mode: the postgres-advisory:// lock is a session-level
# advisory lock and breaks under transaction pooling.
_POOL_OPTIONS = _pool_options(os.environ)

engine = create_engine(
    db_url,
    **_POOL_OPTIONS,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    # A driver error string embeds the statement's bound parameters (hashes, tokens, emails), and the
    # error handler logs it, so they are masked at the engine.
    hide_parameters=True,
    connect_args=_connect_args(os.environ),
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create a base class for declarative models
class Base(DeclarativeBase):
    """Base class for all ORM models."""


# JASIL's companion tables (event_log, event_outbox, processing_jobs) are mapped
# into this registry so one metadata object and one migration run cover the whole
# schema. Both calls must precede any import of a JASIL model module.
jasil_orm.map_models(Base)
jasil_orm.configure_sessionmaker(SessionLocal)


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns.

    Mix into any ORM model that should track record
    creation and modification timestamps. Both columns
    are timezone-aware and maintained by the database
    server, preventing clock-skew issues in distributed
    deployments.

    Attributes:
        created_at: UTC timestamp set when the row is
            first inserted.
        updated_at: UTC timestamp refreshed on every
            UPDATE; mirrors created_at at insertion.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def connection_budget_warning(
    pool_size: int, max_overflow: int, processes: int, *, max_connections: int, reserved: int
) -> str | None:
    """Say so when the pools of this deployment's web processes can hold more connections than PostgreSQL allows.

    Only the processes the caller counts are known here; replicas and dedicated workers each add their own pool,
    so a budget that fits is not proof the whole deployment does.

    Args:
        pool_size: Connections one process's pool keeps open.
        max_overflow: Extra connections one process's pool may open under load.
        processes: How many processes share this configuration.
        max_connections: PostgreSQL's ``max_connections``.
        reserved: PostgreSQL's ``superuser_reserved_connections``, which ordinary roles cannot use.

    Returns:
        The warning to log, or None when the pools fit.
    """
    needed = (pool_size + max_overflow) * processes
    available = max_connections - reserved
    if needed <= available:
        return None
    return (
        f"The database pools of {processes} process(es) can open up to {needed} database connections "
        f"({pool_size} + {max_overflow} each), but PostgreSQL allows {available} for ordinary roles. "
        "Under load requests will fail to get a connection. Lower DB_POOL_SIZE and DB_MAX_OVERFLOW, raise "
        "max_connections, or put PgBouncer in front of the database. Every replica and dedicated worker adds "
        "its own pool to this total."
    )


def pool_processes(*, web_workers: int, jobs_enabled: bool) -> int:
    """Count the processes known to hold a connection pool: the API workers and, with durable jobs, a job worker.

    Args:
        web_workers: How many API worker processes run.
        jobs_enabled: Whether durable jobs run on a dedicated worker process.

    Returns:
        The number of processes, at least one worker being assumed when jobs are enabled.
    """
    return web_workers + (1 if jobs_enabled else 0)


def check_connection_budget(processes: int) -> None:
    """Warn at startup when this process's pool settings can exhaust PostgreSQL's connections.

    A warning only: the pool sizes stay as configured, because the right size depends on how many replicas
    and workers share the database, which only the operator knows.

    Args:
        processes: How many processes share this configuration (``WEB_WORKERS`` for the API).
    """
    with engine.connect() as connection:
        max_connections = int(connection.execute(text("SHOW max_connections")).scalar_one())
        reserved = int(connection.execute(text("SHOW superuser_reserved_connections")).scalar_one())
    warning = connection_budget_warning(
        _POOL_OPTIONS["pool_size"],
        _POOL_OPTIONS["max_overflow"],
        processes,
        max_connections=max_connections,
        reserved=reserved,
    )
    if warning is not None:
        logger.warning(warning, extra=core_logger.context(console=True))


def violated_constraint(err: IntegrityError) -> str | None:
    """Name the constraint an integrity error violated.

    Args:
        err: The integrity error raised by a flush.

    Returns:
        The constraint name the driver reports, or None when it reports none (as SQLite does),
        in which case a caller has only the error text to go on.
    """
    return getattr(getattr(err.orig, "diag", None), "constraint_name", None)


def delete_in_batches(stage_batch: Callable[[int], int], db: Session) -> int:
    """Run a purge one bounded batch per transaction until a batch comes back short.

    Args:
        stage_batch: Stages the deletion of up to the given number of rows and returns how many it staged.
        db: The session the batches run and commit in.

    Returns:
        The number of rows deleted.
    """
    total = 0
    while True:
        deleted = stage_batch(PURGE_BATCH_SIZE)
        db.commit()
        total += deleted
        if deleted < PURGE_BATCH_SIZE:
            return total


def get_db() -> Generator[Session]:
    """
    Yields a new SQLAlchemy database session.

    Rolls back on any unhandled exception so that partial
    writes are never silently committed to the database,
    then closes the session. Intended for use as a
    dependency in FastAPI routes.

    Yields:
        Session: An active SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
