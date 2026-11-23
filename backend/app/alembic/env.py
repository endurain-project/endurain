from contextlib import nullcontext
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError

# import Base and engine from database file
import model_registry as orm_model_registry
from core.database import Base, engine
from migrations.schema_scope import include_object

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


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # A caller that owns the connection (the upgrade tests) passes it in and keeps it open afterwards; Alembic
    # still owns the transaction. Otherwise use the existing engine from database configuration.
    given = config.attributes.get("connection")
    with nullcontext(given) if given is not None else engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    # The upgrade gates read the live database before anything changes, so there is no SQL to write without one.
    raise CommandError("Offline mode (--sql) is not supported: the migrations read the database they upgrade")
run_migrations_online()
