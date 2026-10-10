from logging.config import fileConfig

import jasil.orm as jasil_orm

from alembic import context

# import Base and engine from database file
import model_registry as orm_model_registry
from core.database import Base, engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


# Populate Base.metadata with every ORM model before
# autogenerate compares it against the database. The CLI
# runs only this env.py, which would otherwise leave the
# metadata empty and emit drop_table for the whole schema.
orm_model_registry.import_all_models()

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep this history off the tables JASIL owns.

    ``jasil.orm.map_models`` maps ``event_log``, ``event_outbox`` and
    ``processing_jobs`` into the same registry as the application's own models,
    so autogenerate would otherwise diff them here as well — and propose
    dropping them the day the substrate moves one. They are migrated by
    ``jasil.migrations`` against its own version table instead.

    Args:
        obj: The schema object being considered.
        name: Its name.
        type_: The kind of object (``table``, ``column``, ``index``, ...).
        reflected: Whether it came from the database rather than the metadata.
        compare_to: The object it is being compared against, if any.

    Returns:
        False for a JASIL-owned table, True otherwise.
    """
    if type_ == "table":
        return name not in jasil_orm.jasil_table_names()
    return True


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # Here, instead of creating a new engine, we use the existing engine
    # from database configuration.
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
