from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context


import auth.identity_providers.models
import auth.mfa_backup_codes.models
import auth.oauth_state.models
import activities.activity.models
import activities.activity_exercise_titles.models
import activities.activity_laps.models
import activities.activity_media.models
import activities.activity_sets.models
import activities.activity_streams.models
import activities.activity_workout_steps.models
import followers.models
import gears.gear.models
import gears.gear_components.models
import health_sleep.models
import health_steps.models
import health_targets.models
import health_weight.models
import migrations.models
import notifications.models
import password_reset_tokens.models
import sign_up_tokens.models
import server_settings.models
import session.models
import session.rotated_refresh_tokens.models
import users.user.models
import users.user_goals.models
import users.user_default_gear.models
import users.user_identity_providers.models
import users.user_integrations.models
import users.user_privacy_settings.models

# import Base and engine from database file
from core.database import Base, engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

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
    """ connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    ) """

    # Here, instead of creating a new engine, we use the existing engine
    # from database configuration.
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
