"""Database engine, session factory, and declarative base."""

import os
from collections.abc import Generator
from datetime import datetime

from sqlalchemy import DateTime, create_engine, func
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

import core.config as core_config

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

# Pin the database session timezone to UTC. The import
# parsers emit naive UTC wall-clock timestamps, and the
# datetime columns are TIMESTAMP WITH TIME ZONE. Without
# this, PostgreSQL interprets naive values in the server's
# session timezone (driven by the container TZ env var),
# which shifts stored instants when TZ != UTC. Forcing UTC
# makes storage deterministic regardless of deployment TZ.
_connect_args: dict = {"options": "-c timezone=utc"}

# Optional TLS for the database connection (OWASP A02 —
# Cryptographic Failures). Opt-in via the DB_SSLMODE env
# var so self-hosters running plain Postgres are not
# broken by default. Accepted values match libpq:
# disable | allow | prefer | require | verify-ca |
# verify-full. Recommended for any deployed environment:
# DB_SSLMODE=require (or stricter).
_db_sslmode = os.environ.get("DB_SSLMODE", "").strip().lower()
if _db_sslmode:
    _connect_args["sslmode"] = _db_sslmode

# Create the SQLAlchemy engine.
# Pool budget: pool_size + max_overflow = 60 connections
# per worker. With --workers=N the total is 60*N, which
# must stay below PostgreSQL max_connections (default 100).
# For >1 worker, lower these values or front the database
# with PgBouncer.
engine = create_engine(
    db_url,
    pool_size=20,
    max_overflow=40,
    pool_timeout=180,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create a base class for declarative models
class Base(DeclarativeBase):
    """Base class for all ORM models."""


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
