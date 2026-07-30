import pathlib
from collections.abc import Sequence
from importlib import import_module
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"


def setup_mock_execute(
    mock_db: MagicMock,
    return_all: Sequence[Any] | None = None,
    return_scalar: Any | None = None,
    return_one_or_none: Any | None = None,
    return_scalars_all: Sequence[Any] | None = None,
):
    execute_mock = MagicMock()
    scalars_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    if return_scalars_all is not None:
        scalars_mock.all.return_value = return_scalars_all
    elif return_all is not None:
        scalars_mock.all.return_value = return_all
    if return_scalar is not None:
        scalars_mock.scalar.return_value = return_scalar
    scalars_mock.first.return_value = return_one_or_none
    if return_one_or_none is not None:
        scalars_mock.one_or_none.return_value = return_one_or_none
        execute_mock.scalar_one_or_none.return_value = return_one_or_none
    else:
        execute_mock.scalar_one_or_none.return_value = None
    execute_mock.scalar.return_value = return_scalar
    mock_db.execute.return_value = execute_mock
    # Support db.scalars(stmt) pattern (used by some sub-module CRUDs)
    scalars_direct_mock = MagicMock()
    if return_scalars_all is not None:
        scalars_direct_mock.all.return_value = return_scalars_all
    elif return_all is not None:
        scalars_direct_mock.all.return_value = return_all
    mock_db.scalars.return_value = scalars_direct_mock
    return execute_mock


def setup_mock_query(
    mock_db: MagicMock,
    model_class: type,
    return_all: Sequence[Any] | None = None,
    return_one: Any | None = None,
    return_first: Any | None = None,
    return_scalar: Any | None = None,
    return_count: int = 0,
):
    mock_query = mock_db.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.filter_by.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = return_all if return_all is not None else []
    mock_query.first.return_value = return_first
    mock_query.one.return_value = return_one
    mock_query.one_or_none.return_value = return_one
    mock_query.scalar.return_value = return_scalar if return_scalar is not None else return_count
    mock_query.count.return_value = return_count
    return mock_query


def _import_all_models() -> None:
    """Import every ``models.py`` so the SQLAlchemy mapper registry is complete.

    A real ORM query triggers ``configure_mappers()`` for the whole registry.
    Relationships use string targets, so every related model must be imported
    or configuration fails. ``import_module`` is cached, so repeat calls are
    cheap.
    """
    for path in sorted(_APP_DIR.glob("**/models.py")):
        import_module(".".join(path.relative_to(_APP_DIR).with_suffix("").parts))


def create_sqlite_session() -> Session:
    """Create a real in-memory SQLite session with all tables created.

    Use only for the rare CRUD test that must exercise SQL ``WHERE`` filtering
    behavior, which a mocked ``Session`` cannot evaluate (e.g. access-control
    filters). Prefer the mock-DB helpers for ordinary unit tests. The caller is
    responsible for closing the returned session.
    """
    from core.database import Base

    _import_all_models()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def create_sqlite_session_factory() -> sessionmaker[Session]:
    """Create a sessionmaker over one shared in-memory SQLite engine.

    Unlike ``create_sqlite_session``, sessions produced by this factory share a
    single engine/connection (``StaticPool``), so many short-lived sessions see
    the same data. Use it to test code that opens a fresh session per operation
    (e.g. the durable job runner). Dispose the engine in teardown via
    ``factory.kw["bind"].dispose()`` to avoid a ``ResourceWarning``.
    """
    from core.database import Base

    _import_all_models()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
