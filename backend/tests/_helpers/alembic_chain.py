"""Helpers that run the application's real Alembic history against a test PostgreSQL database."""

from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine

import migrations.startup as migrations_startup
import model_registry as orm_model_registry
from alembic import command
from core.database import Base
from migrations import schema_scope

#: The baseline revision, which is the head of the v0.21.x install, the only supported source of an upgrade to v0.22.
V0_21_HEAD = "e95a7c1d4b36"

_APP_DIR = Path(__file__).resolve().parents[2] / "app"


def alembic_config(connection: Connection | None = None) -> Config:
    """Build the application's Alembic configuration.

    Args:
        connection: A connection ``env.py`` runs on instead of opening its own.

    Returns:
        The configuration of the app's ``alembic.ini`` with an absolute ``script_location``.
    """
    config = Config(str(_APP_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_APP_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    config.attributes["connection"] = connection
    return config


def script_directory() -> ScriptDirectory:
    """Return the revision graph of the application's Alembic history."""
    return ScriptDirectory.from_config(alembic_config())


def upgrade(engine: Engine, revision: str) -> None:
    """Run ``alembic upgrade`` to a revision on a plain connection, so Alembic owns the transaction."""
    with engine.connect() as connection:
        command.upgrade(alembic_config(connection), revision)


def downgrade(engine: Engine, revision: str) -> None:
    """Run ``alembic downgrade`` to a revision on a plain connection, so Alembic owns the transaction."""
    with engine.connect() as connection:
        command.downgrade(alembic_config(connection), revision)


def bootstrap_substrate(engine: Engine) -> None:
    """Adopt, upgrade and verify the substrate's schema, as application startup does after the upgrade."""
    migrations_startup.bootstrap_substrate_schema(engine)


def schema_differences(engine: Engine) -> list:
    """Return what Alembic's autogenerate would change to make the database match the models.

    Args:
        engine: The engine of the database to compare.

    Returns:
        The diff entries of ``compare_metadata``; empty when the schema matches the models.
    """
    orm_model_registry.import_all_models()
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_object": schema_scope.include_object})
        return compare_metadata(context, Base.metadata)


def row_counts(engine: Engine) -> dict[str, int]:
    """Count the rows of every public table inside the autogenerate scope, except ``alembic_version``."""
    with engine.connect() as connection:
        names = sa.inspect(connection).get_table_names(schema="public")
        scoped = [
            name
            for name in sorted(names)
            if name != "alembic_version" and schema_scope.include_object(None, name, "table", True, None)
        ]
        return {
            name: connection.execute(sa.select(sa.func.count()).select_from(sa.table(name))).scalar_one()
            for name in scoped
        }
