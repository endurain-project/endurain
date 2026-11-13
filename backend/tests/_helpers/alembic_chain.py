"""Helpers that run the application's real Alembic chain against a disposable PostgreSQL database."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine

import migrations.startup as migrations_startup
import model_registry as orm_model_registry
from alembic import command
from core.database import Base
from migrations import schema_scope
from tests._helpers.db import disposable_postgres_url

#: The head of the v0.20.x chain, the only supported source of an upgrade to v0.21.
V0_20_HEAD = "d54bdd779392"

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


def upgrade_engine() -> Engine:
    """Create an engine on the disposable database with the session time zone the application pins (UTC).

    Raises:
        RuntimeError: If ``TEST_DATABASE_URL`` is unset or does not name a disposable database.
    """
    return sa.create_engine(disposable_postgres_url(), connect_args={"options": "-c timezone=utc"})


def reset_public_schema(engine: Engine) -> None:
    """Drop and recreate the ``public`` schema, leaving the database empty.

    Raises:
        RuntimeError: If the database name does not contain ``test``.
    """
    database = engine.url.database or ""
    if "test" not in database:
        raise RuntimeError(f"Refusing to drop the public schema of '{database}': it is not a disposable database.")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))


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


_ACTIVITY_CREATED_PAYLOAD = '{"activity_id": 1, "user_id": 1, "duplicate_start_time": false}'


def _execute(connection: Connection, statement: str, **params: str | int) -> None:
    """Run one static INSERT, passing JSON documents as bound parameters."""
    connection.execute(sa.text(statement), params)


def seed_users(connection: Connection) -> None:
    """Insert users 1 (admin), 2 (regular) and 3 (regular), in the shape every revision of the chain accepts."""
    _execute(
        connection,
        """INSERT INTO users (id, name, username, email, preferred_language, email_verified, pending_admin_approval,
               active, gender, access_type, first_day_of_week, units, currency)
           VALUES (1, 'Admin User', 'admin', 'admin@example.com', 'en', true, false, true, 'male', 'admin',
               'monday', 'metric', 'euro'),
               (2, 'Regular User', 'regular', 'regular@example.com', 'en', true, false, true, 'female', 'regular',
               'monday', 'metric', 'euro'),
               (3, 'Third User', 'third', 'third@example.com', 'en', true, false, true, 'female', 'regular',
               'monday', 'metric', 'euro')""",
    )


def _seed_users_local_credentials(connection: Connection) -> None:
    _execute(connection, "INSERT INTO users_local_credentials (user_id, password_hash) VALUES (1, 'seed-hash')")


def _seed_users_mfa(connection: Connection) -> None:
    _execute(connection, "INSERT INTO users_mfa (id, user_id, mfa_enabled) VALUES (1, 1, false)")


def _seed_mfa_backup_codes(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO mfa_backup_codes (id, user_id, code_hash, used, created_at) "
        "VALUES (1, 1, 'seed-backup-code-hash', false, '2024-05-01 10:00:00')",
    )


def _seed_users_privacy_settings(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO users_privacy_settings (id, user_id, hide_activity_start_time, hide_activity_location,
               hide_activity_map, hide_activity_hr, hide_activity_power, hide_activity_cadence,
               hide_activity_elevation, hide_activity_speed, hide_activity_pace, hide_activity_laps,
               hide_activity_workout_sets_steps, hide_activity_gear, default_activity_visibility)
           VALUES (1, 1, false, false, false, false, false, false, false, false, false, false, false, false,
               'public')""",
    )


def _seed_users_integrations(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO users_integrations (id, user_id, strava_sync_gear, garminconnect_sync_gear) "
        "VALUES (1, 1, false, false)",
    )


def _seed_users_goals(connection: Connection) -> None:
    """Seed three goals of user 1, inserted out of id order, with distinct scopes and distances."""
    _execute(
        connection,
        "INSERT INTO users_goals (id, user_id, interval, goal_distance, activity_type, goal_type) "
        "VALUES (3, 1, 'monthly', 30000, 'run', 'distance'), (1, 1, 'weekly', 10000, 'run', 'distance'), "
        "(2, 1, 'daily', 20000, 'ride', 'distance')",
    )


def _seed_users_api_keys(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO users_api_keys (id, user_id, name, key_prefix, key_hash, scopes, created_at, is_active)
           VALUES ('11111111-1111-4111-8111-111111111111', 1, 'seed key', 'edk_seed', 'seed-key-hash',
               'activities:read', '2024-05-01 10:00:00', true)""",
    )


def _seed_identity_providers(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO identity_providers (id, name, slug, provider_type, enabled, auto_create_users, sync_user_info)
           VALUES (1, 'Seed Provider', 'seed-provider', 'oidc', true, false, false)""",
    )


def _seed_users_identity_providers(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO users_identity_providers (id, user_id, idp_id, idp_subject) VALUES (1, 1, 1, 'seed-subject')",
    )


def _seed_idp_link_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO idp_link_tokens (id, user_id, idp_id, expires_at, used, token_hash)
           VALUES ('22222222-2222-4222-8222-222222222222', 1, 1, '2030-01-01 00:00:00', false, 'seed-link-hash')""",
    )


def _seed_oauth_states(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO oauth_states (id, idp_id, user_id, nonce, client_type, expires_at, used)
           VALUES ('seed-oauth-state', 1, 1, 'seed-nonce', 'web', '2030-01-01 00:00:00', false)""",
    )


def _seed_users_sessions(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO users_sessions (id, user_id, ip_address, device_type, operating_system,
               operating_system_version, browser, browser_version, created_at, expires_at, last_activity_at,
               oauth_state_id, tokens_exchanged, token_family_id, rotation_count)
           VALUES ('33333333-3333-4333-8333-333333333333', 1, '127.0.0.1', 'desktop', 'Linux', '6', 'Firefox', '120',
               '2024-05-01 10:00:00', '2030-01-01 00:00:00', '2024-05-01 10:00:00', 'seed-oauth-state', true,
               '44444444-4444-4444-8444-444444444444', 0)""",
    )


def _seed_rotated_refresh_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO rotated_refresh_tokens (id, token_family_id, hashed_token, rotation_count, rotated_at,
               expires_at)
           VALUES (1, '44444444-4444-4444-8444-444444444444', 'seed-rotated-hash', 1, '2024-05-01 10:00:00',
               '2030-01-01 00:00:00')""",
    )


def _seed_password_reset_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO password_reset_tokens (id, user_id, token_hash, created_at, expires_at, used)
           VALUES (:id, 1, 'seed-reset-hash', '2024-05-01 10:00:00', '2030-01-01 00:00:00', false)""",
        id=SEED_RESET_TOKEN_ID,
    )


def _seed_sign_up_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO sign_up_tokens (id, user_id, token_hash, created_at, expires_at, used)
           VALUES (:id, 2, 'seed-signup-hash', '2024-05-01 10:00:00', '2030-01-01 00:00:00',
               false)""",
        id=SEED_SIGN_UP_TOKEN_ID,
    )


def _seed_followers(connection: Connection) -> None:
    """Seed three relationships out of id order: id 2 was created before id 1 and id 3 ties with id 2."""
    _execute(
        connection,
        "INSERT INTO followers (id, follower_id, followee_id, status, created_at) "
        "VALUES (3, 2, 1, 'accepted', '2024-05-01 10:00:01'), (1, 1, 2, 'accepted', '2024-05-01 10:00:02'), "
        "(2, 3, 1, 'accepted', '2024-05-01 10:00:01')",
    )


def _seed_notifications(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO notifications (id, user_id, type, options, read, created_at, source_event_id)
           VALUES (1, 1, 1, CAST(:options AS json), false, '2024-05-01 10:00:00',
               '55555555-5555-4555-8555-555555555555')""",
        options='{"activity_id": 1}',
    )


def _seed_gear(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO gear (id, brand, model, nickname, gear_type, user_id, created_at, initial_kms, active)
           VALUES (1, 'Brand', 'Model', 'Seed bike', 2, 1, '2024-05-01 10:00:00', 0, true)""",
    )


def _seed_gear_components(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO gear_components (id, user_id, gear_id, type, brand, model, purchase_date, active)
           VALUES (1, 1, 1, 'chain', 'Brand', 'Model', '2024-05-01', true)""",
    )


def _seed_users_default_gear(connection: Connection) -> None:
    _execute(connection, "INSERT INTO users_default_gear (id, user_id, ride_gear_id) VALUES (1, 1, 1)")


def _seed_activities(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO activities (id, user_id, name, distance, activity_type, start_time, end_time, created_at,
               visibility, gear_id, total_elapsed_time, total_timer_time, hide_start_time, hide_location, hide_map,
               hide_hr, hide_power, hide_cadence, hide_elevation, hide_speed, hide_pace, hide_laps,
               hide_workout_sets_steps, hide_gear, is_hidden, import_info, version)
           VALUES (1, 1, 'Seed ride', 10000, 2, '2024-05-01 10:00:00', '2024-05-01 11:00:00',
               '2024-05-01 12:00:00', 0, 1, 3600, 3500, false, false, false, false, false, false, false, false,
               false, false, false, false, false, CAST(:import_info AS json), 1)""",
        import_info='{"file_name": "seed.fit"}',
    )


def _seed_activities_streams(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO activities_streams (id, activity_id, stream_type, stream_waypoints) "
        "VALUES (1, 1, 1, CAST(:waypoints AS json))",
        waypoints='[{"time": "2024-05-01T10:00:00", "hr": 120}]',
    )


def _seed_activity_laps(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO activity_laps (id, activity_id, start_time) VALUES (1, 1, '2024-05-01 10:00:00')",
    )


def _seed_activity_media(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO activity_media (id, activity_id, media_path, media_type) VALUES (1, 1, 'seed/media.jpg', 1)",
    )


def _seed_activity_sets(connection: Connection) -> None:
    # Naive on purpose: the column is timestamp without time zone at the v0.20 head.
    _execute(
        connection,
        """INSERT INTO activity_sets (id, activity_id, duration, set_type, start_time)
           VALUES (1, 1, 30, 'active', '2024-05-01 10:00:00')""",
    )


def _seed_activity_workout_steps(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO activity_workout_steps (id, activity_id, message_index, duration_type) VALUES (1, 1, 0, 'time')",
    )


def _seed_activity_exercise_titles(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO activity_exercise_titles (id, exercise_category, exercise_name, wkt_step_name) "
        "VALUES (1, 0, 0, 'Bench press')",
    )


def _seed_activity_ingestion_jobs(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO activity_ingestion_jobs (id, user_id, filename, status, activity_ids, kind)
           VALUES ('66666666-6666-4666-8666-666666666666', 1, 'seed.fit', 'completed', CAST(:activity_ids AS jsonb),
               'upload')""",
        activity_ids="[1]",
    )


def _seed_health_fasting(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO health_fasting (id, user_id, fast_start_time, status) "
        "VALUES (1, 1, '2024-05-01 20:00:00', 'in_progress')",
    )


def _seed_health_poop(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO health_poop (id, user_id, date_time) VALUES (1, 1, '2024-05-01 08:00:00')",
    )


def _seed_health_sleep(connection: Connection) -> None:
    _execute(connection, "INSERT INTO health_sleep (id, user_id, date) VALUES (1, 1, '2024-05-01')")


def _seed_health_steps(connection: Connection) -> None:
    _execute(connection, "INSERT INTO health_steps (id, user_id, date, steps) VALUES (1, 1, '2024-05-01', 8000)")


def _seed_health_targets(connection: Connection) -> None:
    _execute(connection, "INSERT INTO health_targets (id, user_id, steps) VALUES (1, 1, 10000)")


def _seed_health_water(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO health_water (id, user_id, date, amount_ml) VALUES (1, 1, '2024-05-01', 500)",
    )


def _seed_health_weight(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO health_weight (id, user_id, date, weight) VALUES (1, 1, '2024-05-01', 70.5)",
    )


def _seed_event_log(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO event_log (id, event_type, event_source, event_payload, status)
           VALUES ('77777777-7777-4777-8777-777777777777', 'activity.created', 'activities',
               CAST(:payload AS jsonb), 'published')""",
        payload=_ACTIVITY_CREATED_PAYLOAD,
    )


def _seed_event_outbox(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO event_outbox (id, event_id, event_type, source, timestamp, payload)
           VALUES ('88888888-8888-4888-8888-888888888888', '77777777-7777-4777-8777-777777777777',
               'activity.created', 'activities', '2024-05-01T12:00:00+00:00', CAST(:payload AS jsonb))""",
        payload=_ACTIVITY_CREATED_PAYLOAD,
    )


def _seed_processing_jobs(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO processing_jobs (id, event_id, event_type, subscriber_id, source, payload, status, attempts,
               max_attempts)
           VALUES ('99999999-9999-4999-8999-999999999991', '77777777-7777-4777-8777-777777777777',
               'activity.created', 'seed.subscriber.pending', 'activities', CAST(:payload AS jsonb), 'pending', 0, 5),
               ('99999999-9999-4999-8999-999999999992', '77777777-7777-4777-8777-777777777777',
               'activity.created', 'seed.subscriber.dead', 'activities', CAST(:payload AS jsonb), 'dead_letter', 5,
               5)""",
        payload=_ACTIVITY_CREATED_PAYLOAD,
    )


def _mark_data_migrations_executed(connection: Connection) -> None:
    _execute(connection, "UPDATE migrations SET executed = true WHERE id IN (1, 2, 3, 4, 5, 6, 8, 9, 10)")


def seed_v0_20(connection: Connection) -> None:
    """Insert one linked row into every table of the v0.20.x head and mark its data migrations executed.

    The goals and the followers are three each, out of id order.

    The statements are written against the v0.20 head shape and run in dependency order: users first, then what
    refers to them, then the activities and the substrate tables. ``server_settings`` and ``migrations`` are filled
    by the chain itself. Commits are the caller's.

    Args:
        connection: A connection on a database at ``V0_20_HEAD``.
    """
    seed_users(connection)
    _seed_users_local_credentials(connection)
    _seed_users_mfa(connection)
    _seed_mfa_backup_codes(connection)
    _seed_users_privacy_settings(connection)
    _seed_users_integrations(connection)
    _seed_users_goals(connection)
    _seed_users_api_keys(connection)
    _seed_identity_providers(connection)
    _seed_users_identity_providers(connection)
    _seed_idp_link_tokens(connection)
    _seed_oauth_states(connection)
    _seed_users_sessions(connection)
    _seed_rotated_refresh_tokens(connection)
    _seed_password_reset_tokens(connection)
    _seed_sign_up_tokens(connection)
    _seed_followers(connection)
    _seed_notifications(connection)
    _seed_gear(connection)
    _seed_gear_components(connection)
    _seed_users_default_gear(connection)
    _seed_activities(connection)
    _seed_activities_streams(connection)
    _seed_activity_laps(connection)
    _seed_activity_media(connection)
    _seed_activity_sets(connection)
    _seed_activity_workout_steps(connection)
    _seed_activity_exercise_titles(connection)
    _seed_activity_ingestion_jobs(connection)
    _seed_health_fasting(connection)
    _seed_health_poop(connection)
    _seed_health_sleep(connection)
    _seed_health_steps(connection)
    _seed_health_targets(connection)
    _seed_health_water(connection)
    _seed_health_weight(connection)
    _seed_event_log(connection)
    _seed_event_outbox(connection)
    _seed_processing_jobs(connection)
    _mark_data_migrations_executed(connection)


def _seed_v0_21_account_security_generations(connection: Connection) -> None:
    _execute(connection, "INSERT INTO account_security_generations (user_id, generation) VALUES (1, 1)")


def _seed_v0_21_activity_deletions(connection: Connection) -> None:
    _execute(connection, "INSERT INTO activity_deletions (id, user_id, record_id) VALUES (1, 1, 100)")


def _seed_v0_21_gear_deletions(connection: Connection) -> None:
    _execute(connection, "INSERT INTO gear_deletions (id, user_id, record_id) VALUES (1, 1, 100)")


def _seed_v0_21_gear_component_deletions(connection: Connection) -> None:
    _execute(connection, "INSERT INTO gear_component_deletions (id, user_id, record_id) VALUES (1, 1, 100)")


def _seed_v0_21_gear(connection: Connection) -> None:
    """Seed two more gear (one of user 2, one with provider ids), four components out of id order and their references.

    Gear 1 and 2 belong to user 1 and gear 3 to user 2. The default gear of user 1 names gears 1 and 2 in eight
    columns and the default gear of user 2 names gear 3 in the other seven, so every gear column of
    ``users_default_gear`` is set in one row and null in the other. Activity 2 has no gear and activity 3 has gear 2.
    """
    _execute(
        connection,
        """INSERT INTO gear (id, brand, model, nickname, gear_type, user_id, active, initial_distance,
               strava_gear_id, garminconnect_gear_id)
           VALUES (2, 'Brand 2', 'Model 2', 'Second bike', 1, 1, true, 0, 'b12345', 'garmin-gear-2'),
               (3, 'Brand 3', 'Model 3', 'Other user bike', 1, 2, true, 0, NULL, NULL)""",
    )
    _execute(
        connection,
        """INSERT INTO gear_components (id, user_id, gear_id, type, brand, model, purchase_date, active)
           VALUES (2, 1, 2, 'tyre', 'Brand B', 'Model B', '2024-03-01', true),
               (3, 1, 1, 'saddle', 'Brand C', 'Model C', '2024-02-01', false),
               (4, 1, 2, 'pedals', 'Brand D', 'Model D', '2024-01-01', true)""",
    )
    _execute(
        connection,
        """UPDATE users_default_gear
           SET run_gear_id = 1, trail_run_gear_id = 2, virtual_run_gear_id = 1, gravel_ride_gear_id = 2,
               mtb_ride_gear_id = 1, virtual_ride_gear_id = 2, ows_gear_id = 1, walk_gear_id = 2
           WHERE user_id = 1""",
    )
    _execute(
        connection,
        """INSERT INTO users_default_gear (id, user_id, hike_gear_id, tennis_gear_id, alpine_ski_gear_id,
               nordic_ski_gear_id, snowboard_gear_id, windsurf_gear_id, version)
           VALUES (2, 2, 3, 3, 3, 3, 3, 3, 1)""",
    )
    _execute(
        connection,
        """INSERT INTO activities (id, user_id, name, distance, activity_type, start_time, end_time, created_at,
               visibility, gear_id, total_elapsed_time, total_timer_time, hide_start_time, hide_location, hide_map,
               hide_hr, hide_power, hide_cadence, hide_elevation, hide_speed, hide_pace, hide_laps,
               hide_workout_sets_steps, hide_gear, is_hidden, import_info, version)
           VALUES (2, 1, 'Ride without gear', 5000, 2, '2024-05-02 10:00:00', '2024-05-02 11:00:00',
               '2024-05-02 12:00:00', 0, NULL, 3600, 3500, false, false, false, false, false, false, false, false,
               false, false, false, false, false, NULL, 1),
               (3, 1, 'Ride on second bike', 7000, 2, '2024-05-03 10:00:00', '2024-05-03 11:00:00',
               '2024-05-03 12:00:00', 0, 2, 3600, 3500, false, false, false, false, false, false, false, false,
               false, false, false, false, false, NULL, 1)""",
    )


def _seed_v0_21_activity_children(connection: Connection) -> None:
    """Seed the children of activities 1 to 3, in the shape of revision 84, with out-of-id-order media.

    Activities 1 and 3 get a map thumbnail named by their id. Activity 1 gets three laps in start order, two sets, three
    workout steps in ``message_index`` order, two streams and three media rows (ids 4, 2 and 3, inserted out of id
    order) next to the seeded one. Activity 2 gets two streams and activity 3 one lap, two streams and one media row.
    Activity 1 and its first stream carry provider ids.
    """
    _execute(connection, "UPDATE activities SET map_thumbnail_path = id || '.webp' WHERE id IN (1, 3)")
    _execute(
        connection, "UPDATE activities SET strava_activity_id = 12345, garminconnect_activity_id = 67890 WHERE id = 1"
    )
    _execute(
        connection,
        """INSERT INTO activity_laps (id, activity_id, start_time)
           VALUES (2, 1, '2024-05-01 10:10:00'), (3, 1, '2024-05-01 10:20:00'), (4, 3, '2024-05-03 10:00:00')""",
    )
    _execute(
        connection,
        """INSERT INTO activity_sets (id, activity_id, duration, set_type, start_time)
           VALUES (2, 1, 40, 'rest', '2024-05-01 10:00:30')""",
    )
    _execute(
        connection,
        """INSERT INTO activity_workout_steps (id, activity_id, message_index, duration_type)
           VALUES (2, 1, 1, 'time'), (3, 1, 2, 'time')""",
    )
    for stream_id, activity_id, stream_type in ((2, 1, 2), (3, 2, 1), (4, 2, 2), (5, 3, 1), (6, 3, 2)):
        _execute(
            connection,
            "INSERT INTO activities_streams (id, activity_id, stream_type, stream_waypoints) "
            "VALUES (:id, :activity_id, :stream_type, CAST(:waypoints AS json))",
            id=stream_id,
            activity_id=activity_id,
            stream_type=stream_type,
            waypoints=json.dumps([{"time": f"2024-05-0{activity_id}T10:00:00", "value": stream_id * 10}]),
        )
    _execute(connection, "UPDATE activities_streams SET strava_activity_stream_id = 555 WHERE id = 2")
    _execute(
        connection,
        """INSERT INTO activity_media (id, activity_id, media_path, media_type)
           VALUES (4, 1, '1_aaa.jpg', 1), (2, 1, '1_bbb.jpg', 1), (3, 1, '1_ccc.jpg', 1), (5, 3, '3_ddd.jpg', 1)""",
    )


def _seed_v0_21_activity_references(connection: Connection) -> None:
    """Seed the notifications and ingestion jobs that carry activity ids: live, dangling, empty and null ones.

    Notification 1 (source event ``...5555``), 6 (``...5556``) and 7 (``...5557``) name activities 1, 3 and 999.
    """
    for notification_id, notification_type, document in (
        (6, 2, {"activity_id": 3, "activity_name": "Ride on second bike"}),
        (7, 1, {"activity_id": 999}),
    ):
        _execute(
            connection,
            """INSERT INTO notifications (id, user_id, type, options, read, created_at, source_event_id)
               VALUES (:id, 1, :type, CAST(:options AS json), false, '2024-05-01 10:00:00', :source_event_id)""",
            id=notification_id,
            source_event_id=f"55555555-5555-4555-8555-55555555555{notification_id}",
            type=notification_type,
            options=json.dumps(document),
        )
    for job_id, status, activity_ids in (
        ("66666666-6666-4666-8666-666666666667", "pending", "[1, 3]"),
        ("66666666-6666-4666-8666-666666666668", "failed", "[3, 999]"),
        ("66666666-6666-4666-8666-666666666669", "completed", "[]"),
        ("66666666-6666-4666-8666-666666666670", "pending", None),
    ):
        _execute(
            connection,
            """INSERT INTO activity_ingestion_jobs (id, user_id, filename, status, activity_ids, kind)
               VALUES (:id, 1, 'seed.fit', :status, CAST(:activity_ids AS jsonb), 'upload')""",
            id=job_id,
            status=status,
            activity_ids=activity_ids,
        )


def _seed_v0_21_health_record_deletions(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO health_record_deletions (id, user_id, record_id, record_type) VALUES (1, 1, 100, 'health_weight')",
    )


def _seed_v0_21_auth_known_devices(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO auth_known_devices (id, user_id, device_hash, created_at, last_seen_at, security_generation)
           VALUES (1, 1, 'seed-device-hash', '2024-05-01 10:00:00', '2024-05-01 10:00:00', 1)""",
    )


def _seed_v0_21_follow_request_declines(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO follow_request_declines (id, follower_id, followee_id, declined_at) "
        "VALUES (1, 2, 1, '2024-05-01 10:00:00')",
    )


def _seed_v0_21_follower_blocks(connection: Connection) -> None:
    """Seed three blocks inserted out of id order in one transaction, so their ``created_at`` ties."""
    _execute(
        connection,
        "INSERT INTO follower_blocks (id, blocker_id, blocked_id) VALUES (2, 1, 2), (3, 1, 3), (1, 2, 3)",
    )


def _seed_v0_21_mfa_factors(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO mfa_factors (id, user_id, type, credential, created_at) "
        "VALUES (1, 1, 'totp', 'seed-credential', '2024-05-01 10:00:00')",
    )


def _seed_v0_21_oauth_states(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO oauth_states (id, idp_id, user_id, nonce, client_type, expires_at, used, purpose)
           VALUES ('seed-oauth-state', 1, 1, 'seed-nonce', 'web', '2030-01-01 00:00:00', false, 'login')""",
    )


def _seed_v0_21_users_sessions(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO users_sessions (id, user_id, ip_address, device_type, operating_system,
               operating_system_version, browser, browser_version, created_at, expires_at, last_activity_at,
               oauth_state_id, tokens_exchanged, token_family_id, rotation_count, client_type, auth_time, amr)
           VALUES ('33333333-3333-4333-8333-333333333333', 1, '127.0.0.1', 'desktop', 'Linux', '6', 'Firefox', '120',
               '2024-05-01 10:00:00', '2030-01-01 00:00:00', '2024-05-01 10:00:00', 'seed-oauth-state', true,
               '44444444-4444-4444-8444-444444444444', 0, 'web', '2024-05-01 10:00:00', CAST(:amr AS json))""",
        amr='["pwd"]',
    )


def _seed_v0_21_rotated_refresh_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO rotated_refresh_tokens (id, token_family_id, hashed_token, rotation_count, rotated_at,
               expires_at, refresh_token_exp, client_fingerprint)
           VALUES (1, '44444444-4444-4444-8444-444444444444', 'seed-rotated-hash', 1, '2024-05-01 10:00:00',
               '2030-01-01 00:00:00', '2030-01-01 00:00:00', 'seed-fingerprint')""",
    )


def _seed_v0_21_idp_session_tokens(connection: Connection) -> None:
    _execute(
        connection,
        "INSERT INTO idp_session_tokens (id, session_id, user_id, idp_id) "
        "VALUES (1, '33333333-3333-4333-8333-333333333333', 1, 1)",
    )


def _seed_v0_21_second_identity_provider(connection: Connection) -> None:
    """Seed provider 2 with a link of user 2, a session token and an OAuth state, and a state with no provider."""
    _execute(
        connection,
        """INSERT INTO identity_providers (id, name, slug, provider_type, enabled, auto_create_users, sync_user_info)
           VALUES (2, 'Second Provider', 'second-provider', 'oidc', true, false, false)""",
    )
    _execute(
        connection,
        "INSERT INTO users_identity_providers (id, user_id, idp_id, idp_subject) VALUES (2, 2, 2, 'second-subject')",
    )
    _execute(
        connection,
        "INSERT INTO idp_session_tokens (id, session_id, user_id, idp_id) "
        "VALUES (2, '33333333-3333-4333-8333-333333333332', 2, 2)",
    )
    _execute(
        connection,
        """INSERT INTO oauth_states (id, idp_id, user_id, nonce, client_type, expires_at, used, purpose)
           VALUES ('seed-oauth-state-2', 2, 2, 'seed-nonce', 'web', '2030-01-01 00:00:00', false, 'login'),
               ('seed-oauth-state-no-idp', NULL, NULL, 'seed-nonce', 'mobile', '2030-01-01 00:00:00', false,
                'login')""",
    )


def _seed_v0_21_idp_notifications(connection: Connection) -> None:
    """Seed the notifications that carry an ``idp_id`` in their options: a live, a dangling and a null one."""
    options = (
        (2, 31, {"idp_id": 2, "idp_name": "Second"}),
        (3, 31, {"idp_id": 99, "idp_name": None}),
        (4, 32, {"change": "identity_provider_unlinked", "idp_id": 1, "idp_name": "Seed Provider"}),
        (5, 32, {"change": "password_changed", "idp_id": None}),
    )
    for notification_id, notification_type, document in options:
        _execute(
            connection,
            """INSERT INTO notifications (id, user_id, type, options, read, created_at)
               VALUES (:id, 1, :type, CAST(:options AS json), false, '2024-05-01 10:00:00')""",
            id=notification_id,
            type=notification_type,
            options=json.dumps(document),
        )


def _reference_id(index: int) -> str:
    """Return a fixed UUID for a row seeded on a database at revision 90."""
    return f"00000000-0000-4000-8000-{index:012d}"


#: The ids of the password-reset and sign-up tokens and of the sessions seeded at revision 90, by user.
SEED_RESET_TOKEN_ID = _reference_id(1800)
SEED_SIGN_UP_TOKEN_ID = _reference_id(1801)
RESET_TOKEN_IDS = {2: _reference_id(1812), 3: _reference_id(1813)}
EMAIL_CHANGE_TOKEN_IDS = {1: _reference_id(1821), 3: _reference_id(1823)}
#: The id of a re-issued email-change link of user 1: its ``change_id`` names the first token of the change.
REISSUED_EMAIL_CHANGE_TOKEN_ID = _reference_id(1824)
SESSION_IDS = {2: _reference_id(1832), 3: _reference_id(1833)}
TOKEN_FAMILY_IDS = {2: _reference_id(1842), 3: _reference_id(1843)}


def _insert_rows(
    connection: Connection, table: str, rows: Sequence[dict[str, object]], json_columns: Sequence[str] = ()
) -> None:
    """Insert rows into a table, each given as a dict of column to value."""
    for row in rows:
        target = sa.table(table, *(sa.column(name, sa.JSON if name in json_columns else None) for name in row))
        connection.execute(sa.insert(target).values(row))


def _provider_id(connection: Connection, slug: str) -> str:
    return str(
        connection.execute(sa.text("SELECT id FROM identity_providers WHERE slug = :slug"), {"slug": slug}).scalar()
    )


def _seed_users_references_health(connection: Connection) -> None:
    for number, user_id in enumerate((2, 3), start=1):
        day = f"2024-05-0{number + 1}"
        _insert_rows(
            connection,
            "health_fasting",
            [
                {
                    "id": _reference_id(1100 + number),
                    "user_id": user_id,
                    "fast_start_time": f"{day} 20:00:00",
                    "status": "in_progress" if user_id == 2 else "completed",
                }
            ],
        )
        _insert_rows(
            connection,
            "health_poop",
            [{"id": _reference_id(1110 + number), "user_id": user_id, "date_time": f"{day} 08:00:00"}],
        )
        _insert_rows(
            connection, "health_sleep", [{"id": _reference_id(1120 + number), "user_id": user_id, "date": day}]
        )
        _insert_rows(
            connection,
            "health_steps",
            [{"id": _reference_id(1130 + number), "user_id": user_id, "date": day, "steps": 1000 * user_id}],
        )
        _insert_rows(
            connection,
            "health_targets",
            [{"id": _reference_id(1140 + number), "user_id": user_id, "steps": 5000 * user_id}],
        )
        _insert_rows(
            connection,
            "health_water",
            [{"id": _reference_id(1150 + number), "user_id": user_id, "date": day, "amount_ml": 250 * user_id}],
        )
        _insert_rows(
            connection,
            "health_weight",
            [{"id": _reference_id(1160 + number), "user_id": user_id, "date": day, "weight_kg": 60 + user_id}],
        )
    for number, user_id in enumerate((1, 2, 3), start=1):
        _insert_rows(
            connection,
            "health_record_deletions",
            [
                {
                    "id": _reference_id(1170 + number),
                    "user_id": user_id,
                    "record_id": _reference_id(1180 + number),
                    "record_type": "health_weight",
                }
            ],
        )


def _seed_users_references_gear(connection: Connection) -> None:
    _insert_rows(
        connection,
        "gear",
        [
            {
                "id": _reference_id(1200 + user_id),
                "nickname": f"Bike of user {user_id}",
                "gear_type": 1,
                "user_id": user_id,
                "initial_distance": 0,
                "active": True,
                "strava_gear_id": f"strava-gear-{user_id}",
                "garminconnect_gear_id": f"garmin-gear-{user_id}",
            }
            for user_id in (2, 3)
        ],
    )
    _insert_rows(
        connection,
        "gear_components",
        [
            {
                "id": _reference_id(1210 + user_id),
                "user_id": user_id,
                "gear_id": _reference_id(1200 + user_id),
                "type": "chain",
                "brand": "Brand",
                "model": f"Component of user {user_id}",
                "purchase_date": "2024-05-01",
                "active": True,
            }
            for user_id in (2, 3)
        ],
    )
    for number, user_id in enumerate((1, 2, 3), start=1):
        for table, offset in (
            ("gear_deletions", 1220),
            ("gear_component_deletions", 1230),
            ("activity_deletions", 1240),
        ):
            _insert_rows(
                connection,
                table,
                [
                    {
                        "id": _reference_id(offset + number),
                        "user_id": user_id,
                        "record_id": _reference_id(offset + 5 + number),
                    }
                ],
            )
    _insert_rows(
        connection,
        "users_default_gear",
        [{"id": _reference_id(1250), "user_id": 3, "version": 1}],
    )


def _seed_users_references_activities(connection: Connection) -> None:
    for user_id in (2, 3):
        _insert_rows(
            connection,
            "activities",
            [
                {
                    "id": _reference_id(1300 + user_id),
                    "user_id": user_id,
                    "name": f"Ride of user {user_id}",
                    "distance": 1000 * user_id,
                    "activity_type": 2,
                    "start_time": "2024-05-04 10:00:00",
                    "end_time": "2024-05-04 11:00:00",
                    "created_at": "2024-05-04 12:00:00",
                    "visibility": 0,
                    "total_elapsed_time": 3600,
                    "total_timer_time": 3500,
                    "hide_start_time": False,
                    "hide_location": False,
                    "hide_map": False,
                    "hide_hr": False,
                    "hide_power": False,
                    "hide_cadence": False,
                    "hide_elevation": False,
                    "hide_speed": False,
                    "hide_pace": False,
                    "hide_laps": False,
                    "hide_workout_sets_steps": False,
                    "hide_gear": False,
                    "is_hidden": False,
                    "dedup_key": f"dedup-{user_id}",
                    "version": 1,
                }
            ],
        )
    _insert_rows(
        connection,
        "activity_ingestion_jobs",
        [
            {
                "id": "66666666-6666-4666-8666-666666666680",
                "user_id": 2,
                "filename": "bulk.zip",
                "status": "pending",
                "kind": "bulk_import",
            },
            {
                "id": "66666666-6666-4666-8666-666666666681",
                "user_id": 3,
                "filename": "third.fit",
                "status": "completed",
                "kind": "upload",
            },
        ],
    )


def _seed_users_references_social(connection: Connection) -> None:
    _insert_rows(
        connection,
        "followers",
        [
            {
                "id": _reference_id(1400),
                "follower_id": 2,
                "followee_id": 3,
                "status": "accepted",
                "created_at": "2024-05-01 10:00:03",
            }
        ],
    )
    _insert_rows(connection, "follower_blocks", [{"id": _reference_id(1410), "blocker_id": 3, "blocked_id": 1}])
    _insert_rows(
        connection,
        "follow_request_declines",
        [
            {"id": _reference_id(1420), "follower_id": 3, "followee_id": 2, "declined_at": "2024-05-01 10:00:01"},
            {"id": _reference_id(1421), "follower_id": 1, "followee_id": 3, "declined_at": "2024-05-01 10:00:02"},
        ],
    )
    _insert_rows(
        connection,
        "users_goals",
        [
            {
                "id": _reference_id(1430 + user_id),
                "user_id": user_id,
                "interval": "weekly",
                "goal_distance": 1000 * user_id,
                "activity_type": "run",
                "goal_type": "distance",
            }
            for user_id in (2, 3)
        ],
    )


def _seed_users_references_accounts(connection: Connection) -> None:
    _insert_rows(
        connection,
        "account_security_generations",
        [{"user_id": 2, "generation": 2}, {"user_id": 3, "generation": 3}],
    )
    _insert_rows(
        connection,
        "users_local_credentials",
        [
            {"user_id": 2, "password_hash": "second-hash"},
            {"user_id": 3, "password_hash": "third-hash"},
        ],
    )
    _insert_rows(
        connection,
        "users_integrations",
        [{"id": _reference_id(1500 + user_id), "user_id": user_id, "strava_sync_gear": False} for user_id in (2, 3)],
    )
    privacy = {
        f"hide_activity_{name}": False
        for name in (
            "start_time",
            "location",
            "map",
            "hr",
            "power",
            "cadence",
            "elevation",
            "speed",
            "pace",
            "laps",
            "workout_sets_steps",
            "gear",
        )
    }
    _insert_rows(
        connection,
        "users_privacy_settings",
        [
            {
                "id": _reference_id(1510 + user_id),
                "user_id": user_id,
                **privacy,
                "default_activity_visibility": "public",
            }
            for user_id in (2, 3)
        ],
    )
    _insert_rows(
        connection,
        "users_identity_providers",
        [
            {
                "id": _reference_id(1520),
                "user_id": 3,
                "idp_id": _provider_id(connection, "seed-provider"),
                "idp_subject": "third-subject",
            }
        ],
    )
    for user_id in (2, 3):
        _insert_rows(
            connection,
            "mfa_backup_codes",
            [
                {
                    "id": _reference_id(1530 + user_id),
                    "user_id": user_id,
                    "code_hash": f"backup-code-hash-{user_id}",
                    "used": False,
                    "created_at": "2024-05-01 10:00:00",
                }
            ],
        )
        _insert_rows(
            connection,
            "mfa_factors",
            [
                {
                    "id": _reference_id(1540 + user_id),
                    "user_id": user_id,
                    "type": "totp",
                    "credential": f"credential-{user_id}",
                    "created_at": "2024-05-01 10:00:00",
                }
            ],
        )
        _insert_rows(
            connection,
            "auth_known_devices",
            [
                {
                    "id": _reference_id(1550 + user_id),
                    "user_id": user_id,
                    "device_hash": f"device-hash-{user_id}",
                    "created_at": "2024-05-01 10:00:00",
                    "last_seen_at": "2024-05-01 10:00:00",
                    "security_generation": 1,
                }
            ],
        )
        _insert_rows(
            connection,
            "users_api_keys",
            [
                {
                    "id": f"1111111{user_id}-1111-4111-8111-111111111111",
                    "user_id": user_id,
                    "name": f"key of user {user_id}",
                    "key_prefix": f"edk_{user_id}",
                    "key_hash": f"key-hash-{user_id}",
                    "scopes": "activities:read",
                    "expires_at": "2030-01-01 00:00:00",
                    "created_at": "2024-05-01 10:00:00",
                    "is_active": True,
                }
            ],
        )


def _seed_users_references_tokens_and_sessions(connection: Connection) -> None:
    for user_id in (2, 3):
        _insert_rows(
            connection,
            "password_reset_tokens",
            [
                {
                    "id": RESET_TOKEN_IDS[user_id],
                    "user_id": user_id,
                    "token_hash": f"reset-hash-{user_id}",
                    "created_at": "2024-05-01 10:00:00",
                    "expires_at": "2030-01-01 00:00:00",
                    "used": False,
                }
            ],
        )
    for user_id, previous_email in ((1, "admin@example.com"), (3, "third@example.com")):
        _insert_rows(
            connection,
            "sign_up_tokens",
            [
                {
                    "id": EMAIL_CHANGE_TOKEN_IDS[user_id],
                    "user_id": user_id,
                    "token_hash": f"email-change-hash-{user_id}",
                    "created_at": "2024-05-01 10:00:00",
                    "expires_at": "2030-01-01 00:00:00",
                    "used": False,
                    "email": f"new-{user_id}@example.com",
                    "previous_email": previous_email,
                    "security_generation": 1,
                    "change_id": EMAIL_CHANGE_TOKEN_IDS[user_id],
                    "revert_until": "2030-01-01 00:00:00",
                }
            ],
        )
    _insert_rows(
        connection,
        "sign_up_tokens",
        [
            {
                "id": REISSUED_EMAIL_CHANGE_TOKEN_ID,
                "user_id": 1,
                "token_hash": "email-change-hash-1-reissued",
                "created_at": "2024-05-01 11:00:00",
                "expires_at": "2030-01-01 00:00:00",
                "used": False,
                "email": "new-1@example.com",
                "previous_email": "admin@example.com",
                "security_generation": 1,
                "change_id": EMAIL_CHANGE_TOKEN_IDS[1],
                "revert_until": "2030-01-01 00:00:00",
            }
        ],
    )
    for user_id in (2, 3):
        _insert_rows(
            connection,
            "users_sessions",
            [
                {
                    "id": SESSION_IDS[user_id],
                    "user_id": user_id,
                    "ip_address": "127.0.0.1",
                    "device_type": "desktop",
                    "operating_system": "Linux",
                    "operating_system_version": "6",
                    "browser": "Firefox",
                    "browser_version": "120",
                    "created_at": "2024-05-01 10:00:00",
                    "expires_at": "2030-01-01 00:00:00",
                    "last_activity_at": "2024-05-01 10:00:00",
                    "tokens_exchanged": True,
                    "token_family_id": TOKEN_FAMILY_IDS[user_id],
                    "rotation_count": 0,
                    "client_type": "web",
                    "auth_time": "2024-05-01 10:00:00",
                    "amr": ["pwd"],
                }
            ],
            json_columns=("amr",),
        )
    _insert_rows(
        connection,
        "oauth_states",
        [
            {
                "id": "seed-oauth-state-3",
                "idp_id": _provider_id(connection, "seed-provider"),
                "user_id": 3,
                "nonce": "seed-nonce",
                "client_type": "web",
                "expires_at": "2030-01-01 00:00:00",
                "used": False,
                "purpose": "login",
            }
        ],
    )
    _insert_rows(
        connection,
        "idp_session_tokens",
        [
            {
                "id": _reference_id(1600),
                "session_id": SESSION_IDS[3],
                "user_id": 3,
                "idp_id": _provider_id(connection, "seed-provider"),
            }
        ],
    )


#: The notifications seeded at revision 90, as (index, owner, type, options): the ones that name a user in their
#: options (a follower notification), a dangling user and options that carry no user id.
USER_NOTIFICATIONS: tuple[tuple[int, int, int, dict[str, object] | None], ...] = (
    (1, 1, 11, {"user_id": 2, "username": "regular"}),
    (2, 2, 12, {"user_id": 1, "other": "kept"}),
    (3, 3, 11, {"user_id": 999, "username": "gone"}),
    (4, 3, 1, {"activity_id": "kept"}),
    (5, 2, 1, None),
    (6, 3, 12, {"user_id": None}),
)


#: The sessions seeded by ``seed_text_ids`` on a database at revision 91: (session id, token family id).
TEXT_ID_SESSIONS = ((_reference_id(1900), _reference_id(1910)), (_reference_id(1901), _reference_id(1911)))


def seed_text_ids(connection: Connection) -> None:
    """Insert the rows that hold the UUID text of the revision 92 columns, on a database at revision 91.

    Revision 91 emptied the sessions, the rotated refresh tokens, the OAuth states and the identity provider session
    tokens. This fills them again: two sessions with their token families, rotated tokens in both families, OAuth
    states that name a session (a link and a step-up flow) and one that names none, and session tokens naming the
    sessions. The API keys, ingestion jobs and password-reset and sign-up tokens are seeded by the earlier seeders.
    Commits are the caller's.

    Args:
        connection: A connection on a database at ``353455bea2a5``.
    """
    user_id = connection.execute(sa.text("SELECT id FROM users WHERE username = 'admin'")).scalar_one()
    idp_id = _provider_id(connection, "seed-provider")
    for session_id, family_id in TEXT_ID_SESSIONS:
        _insert_rows(
            connection,
            "users_sessions",
            [
                {
                    "id": session_id,
                    "user_id": user_id,
                    "ip_address": "127.0.0.1",
                    "device_type": "desktop",
                    "operating_system": "Linux",
                    "operating_system_version": "6",
                    "browser": "Firefox",
                    "browser_version": "120",
                    "created_at": "2024-05-01 10:00:00",
                    "expires_at": "2030-01-01 00:00:00",
                    "last_activity_at": "2024-05-01 10:00:00",
                    "tokens_exchanged": True,
                    "token_family_id": family_id,
                    "rotation_count": 0,
                    "client_type": "web",
                    "auth_time": "2024-05-01 10:00:00",
                    "amr": ["pwd"],
                }
            ],
            json_columns=("amr",),
        )
    for number, (_, family_id) in enumerate(TEXT_ID_SESSIONS, start=1):
        _insert_rows(
            connection,
            "rotated_refresh_tokens",
            [
                {
                    "id": _reference_id(1920 + number),
                    "token_family_id": family_id,
                    "hashed_token": f"text-id-rotated-hash-{number}",
                    "rotation_count": 1,
                    "rotated_at": "2024-05-01 10:00:00",
                    "expires_at": "2030-01-01 00:00:00",
                    "refresh_token_exp": "2030-01-01 00:00:00",
                    "client_fingerprint": "seed-fingerprint",
                }
            ],
        )
    session_ids = [session_id for session_id, _ in TEXT_ID_SESSIONS]
    _insert_rows(
        connection,
        "oauth_states",
        [
            {
                "id": f"text-id-state-{purpose}",
                "idp_id": idp_id,
                "user_id": user_id,
                "nonce": "seed-nonce",
                "client_type": "web",
                "expires_at": "2030-01-01 00:00:00",
                "used": False,
                "purpose": purpose,
                "session_id": session_id,
            }
            for purpose, session_id in (("link", session_ids[0]), ("step_up", session_ids[1]), ("login", None))
        ],
    )
    for number, session_id in enumerate(session_ids, start=1):
        _insert_rows(
            connection,
            "idp_session_tokens",
            [{"id": _reference_id(1930 + number), "session_id": session_id, "user_id": user_id, "idp_id": idp_id}],
        )


def _seed_users_references_notifications(connection: Connection) -> None:
    for index, owner, notification_type, options in USER_NOTIFICATIONS:
        connection.execute(
            sa.text(
                """INSERT INTO notifications (id, user_id, type, options, read, created_at)
                   VALUES (:id, :owner, :type, CAST(:options AS json), false, '2024-05-01 10:00:00')"""
            ),
            {
                "id": _reference_id(1700 + index),
                "owner": owner,
                "type": notification_type,
                "options": None if options is None else json.dumps(options),
            },
        )


def seed_users_references(connection: Connection) -> None:
    """Give every column that references ``users`` rows naming users 1, 2 and 3, on a database at revision 90.

    Adds to what ``seed_v0_20`` and ``seed_v0_21`` seeded: a pending email change and a password reset token, API
    keys, tombstones, the rows of the two ``user_id`` primary-key tables, an active bulk import, an in-progress
    fast, a TOTP factor and a self-contained set of notifications whose options name a user. Commits are the caller's.

    Args:
        connection: A connection on a database at ``3ab6649cdd08``.
    """
    _seed_users_references_health(connection)
    _seed_users_references_gear(connection)
    _seed_users_references_activities(connection)
    _seed_users_references_social(connection)
    _seed_users_references_accounts(connection)
    _seed_users_references_tokens_and_sessions(connection)
    _seed_users_references_notifications(connection)


#: The events the identity-provider revision rewrites, plus one control of another type that must stay as it is, as
#: (event type, payload). The ``idp_id`` is the old integer id: 1 and 2 name seeded providers, 99 names none.
IDP_EVENT_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("auth.idp_linked", {"user_id": 1, "idp_id": 2}),
    ("auth.account_security_changed", {"user_id": 1, "change": "identity_provider_unlinked", "idp_id": 1}),
    ("auth.account_security_changed", {"user_id": 1, "change": "password_changed", "idp_id": None}),
    ("auth.account_security_changed", {"user_id": 1, "change": "identity_provider_unlinked", "idp_id": 99}),
    ("activity.created", {"activity_id": 1, "user_id": 1, "idp_id": 2}),
)
#: The metadata of every seeded identity-provider event row.
IDP_EVENT_METADATA: dict[str, object] = {"user_id": 1, "request_id": "seed"}
#: The id prefix of the identity-provider event rows: ``idp-event-<index>`` in the event log, ``idp-outbox-<index>-...``
#: in the outbox and ``idp-job-<index>-<state>`` in the processing jobs.
IDP_EVENT_PREFIX = "idp"
#: The events the activities revision rewrites, as (event type, payload): ``activity_id`` 1 and 3 name seeded
#: activities, 999 names none; the control is an event of another type that carries an integer ``activity_id`` and
#: must stay as it is.
ACTIVITY_EVENT_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("activity.created", {"activity_id": 1, "user_id": 1, "duplicate_start_time": False}),
    ("activity.updated", {"activity_id": 3, "user_id": 1, "changed_fields": ["name"]}),
    ("activity.deleted", {"activity_id": 999}),
    ("auth.idp_linked", {"user_id": 1, "idp_id": 2, "activity_id": 1}),
)
#: The metadata of every seeded activity event row.
ACTIVITY_EVENT_METADATA: dict[str, object] = {"activity_id": 1, "user_id": 1, "request_id": "seed"}
#: The id prefix of the activity event rows, laid out as ``IDP_EVENT_PREFIX`` is.
ACTIVITY_EVENT_PREFIX = "act"
#: The user id fields of every event type the users revision rewrites, as (event type, fields), read from the payload
#: classes. Each field of a case names a different seeded user.
_USER_EVENT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("activity.created", ("user_id",)),
    ("activity.updated", ("user_id",)),
    ("activities.visibility_edit_requested", ("user_id",)),
    ("auth.account_security_changed", ("user_id",)),
    ("auth.step_up_session_ended", ("user_id",)),
    ("auth.step_up_locked", ("user_id",)),
    ("auth.account_locked", ("user_id",)),
    ("auth.mfa_locked", ("user_id",)),
    ("auth.refresh_reuse_detected", ("user_id",)),
    ("auth.idp_linked", ("user_id",)),
    ("auth.idp_token_refresh_requested", ("user_id",)),
    ("auth.new_device_sign_in", ("user_id",)),
    ("auth.backup_code_used", ("user_id",)),
    ("auth.password_reset_requested", ("user_id",)),
    ("auth.password_reset_completed", ("user_id",)),
    ("auth.sessions_revoked", ("user_id",)),
    ("auth.sign_up_verification_requested", ("user_id",)),
    ("auth.admin_invitation_requested", ("user_id",)),
    ("auth.email_change_verification_requested", ("user_id",)),
    ("auth.sign_up_approved", ("user_id",)),
    ("auth.sign_up_existing_account", ("user_id",)),
    ("auth.email_change_requested", ("user_id",)),
    ("auth.email_change_address_taken", ("user_id",)),
    ("auth.email_changed", ("user_id",)),
    ("auth.sign_up_approval_requested", ("user_id", "admin_user_id")),
    ("follower.requested", ("requester_user_id", "target_user_id")),
    ("follower.accepted", ("accepter_user_id", "requester_user_id")),
    ("follower.request_removed", ("requester_user_id", "target_user_id")),
    ("garmin.sync_requested", ("user_id",)),
    ("strava.sync_requested", ("user_id",)),
    ("users.deletion_requested", ("user_id",)),
    ("users.admin_promoted", ("user_id", "admin_user_id")),
    ("users.profile_import_requested", ("user_id",)),
    ("users.profile_export_requested", ("user_id",)),
)


def _user_event_payload(index: int, event_type: str, fields: tuple[str, ...]) -> dict[str, object]:
    """Return the payload of a seeded user event: each user field names a seeded user, beside a ``marker``.

    A profile import event also carries the ``staged_key`` of the archive, in the integer layout of the user it names.
    """
    payload: dict[str, object] = {field: (index + offset) % 3 + 1 for offset, field in enumerate(fields)}
    if event_type == "users.profile_import_requested":
        payload["staged_key"] = f"{payload['user_id']}/archive.zip"
    return {**payload, "marker": f"kept-{index}"}


#: The events the users revision rewrites, as (event type, payload): one per type, each user field naming a seeded user
#: (1, 2 or 3) with a field that is not rewritten beside it; then a password reset with a null user, one with a user
#: that does not exist (999), a user id that is text, and a control of another type that must stay as it is.
USER_EVENT_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    *(
        (event_type, _user_event_payload(index, event_type, fields))
        for index, (event_type, fields) in enumerate(_USER_EVENT_FIELDS)
    ),
    ("auth.password_reset_requested", {"user_id": None, "marker": "null"}),
    ("auth.password_reset_requested", {"user_id": 999, "marker": "dangling"}),
    ("auth.mfa_locked", {"user_id": "already-text", "marker": "text"}),
    ("activity.deleted", {"user_id": 1, "marker": "control"}),
)
#: The metadata of every seeded user event row: user 2 is named, so the rewrite is told apart from user 1.
USER_EVENT_METADATA: dict[str, object] = {"user_id": 2, "request_id": "seed"}
#: One event whose metadata names a user that does not exist.
USER_EVENT_DANGLING_METADATA_CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ("auth.sessions_revoked", {"user_id": 3, "marker": "dangling metadata"}),
)
USER_EVENT_DANGLING_METADATA: dict[str, object] = {"user_id": 999, "request_id": "seed"}
#: The id prefixes of the user event rows, laid out as ``IDP_EVENT_PREFIX`` is.
USER_EVENT_PREFIX = "usr"
USER_EVENT_DANGLING_PREFIX = "usd"
#: The states of the seeded processing jobs; ``retrying`` is a pending job that was attempted.
EVENT_JOB_STATES = ("pending", "retrying", "claimed", "dead_letter", "completed")


def seed_events(
    connection: Connection,
    cases: Sequence[tuple[str, dict[str, object]]],
    metadata: dict[str, object],
    id_prefix: str,
    table_prefix: str = "",
) -> None:
    """Seed one event row per case in every substrate table, in each state a row can be in.

    The outbox gets an unrelayed and a relayed row per case, the processing jobs one row per case and state, the
    event log one row per case. Every row carries ``metadata``. The ids are ``<id_prefix>-event-<index>`` in the log,
    ``<id_prefix>-outbox-<index>-<relayed>`` in the outbox and ``<id_prefix>-job-<index>-<state>`` in the jobs.

    Args:
        connection: A connection on the database.
        cases: The (event type, payload) of each event.
        metadata: The metadata of every row.
        id_prefix: The prefix of the row ids.
        table_prefix: The prefix of the substrate table names: empty before JASIL renames them, ``jasil_`` after.
    """
    jsonb = postgresql.JSONB
    log = sa.table(
        f"{table_prefix}event_log",
        *(sa.column(name) for name in ("id", "event_type", "event_source", "status")),
        sa.column("event_payload", jsonb),
        sa.column("event_metadata", jsonb),
    )
    outbox = sa.table(
        f"{table_prefix}event_outbox",
        *(sa.column(name) for name in ("id", "event_id", "event_type", "source", "timestamp", "relayed_at")),
        sa.column("payload", jsonb),
        sa.column("event_metadata", jsonb),
    )
    jobs = sa.table(
        f"{table_prefix}processing_jobs",
        *(
            sa.column(name)
            for name in (
                "id",
                "event_id",
                "event_type",
                "subscriber_id",
                "source",
                "status",
                "attempts",
                "max_attempts",
            )
        ),
        sa.column("payload", jsonb),
        sa.column("job_metadata", jsonb),
    )
    numbered = list(enumerate(cases))
    event_ids = [f"{id_prefix}-event-{index}" for index, _ in numbered]
    connection.execute(
        sa.insert(log),
        [
            {
                "id": event_ids[index],
                "event_type": event_type,
                "event_source": "seed",
                "status": "published",
                "event_payload": payload,
                "event_metadata": metadata,
            }
            for index, (event_type, payload) in numbered
        ],
    )
    connection.execute(
        sa.insert(outbox),
        [
            {
                "id": f"{id_prefix}-outbox-{index}-{relayed}",
                "event_id": f"{event_ids[index]}-{relayed}",
                "event_type": event_type,
                "source": "seed",
                "timestamp": "2024-05-01T12:00:00+00:00",
                "relayed_at": datetime(2024, 5, 1, 12, tzinfo=UTC) if relayed else None,
                "payload": payload,
                "event_metadata": metadata,
            }
            for index, (event_type, payload) in numbered
            for relayed in (False, True)
        ],
    )
    connection.execute(
        sa.insert(jobs),
        [
            {
                "id": f"{id_prefix}-job-{index}-{state}",
                "event_id": event_ids[index],
                "event_type": event_type,
                "subscriber_id": f"seed.subscriber.{state}",
                "source": "seed",
                "status": "pending" if state == "retrying" else state,
                "attempts": 2 if state == "retrying" else 0,
                "max_attempts": 5,
                "payload": payload,
                "job_metadata": metadata,
            }
            for index, (event_type, payload) in numbered
            for state in EVENT_JOB_STATES
        ],
    )


def seed_v0_21(connection: Connection) -> None:
    """Insert one row into every table the v0.21 chain creates or empties, on a database at revision 84.

    Run after ``seed_v0_20`` and the upgrade to ``b84e9f3a6c25``. Revision 7x purges ``oauth_states``,
    ``users_sessions`` and ``rotated_refresh_tokens`` along the way, so they are filled again here in the shape of
    revision 84. Commits are the caller's.

    Args:
        connection: A connection on a database at ``b84e9f3a6c25``.
    """
    _seed_v0_21_account_security_generations(connection)
    _seed_v0_21_activity_deletions(connection)
    _seed_v0_21_gear_deletions(connection)
    _seed_v0_21_gear_component_deletions(connection)
    _seed_v0_21_gear(connection)
    _seed_v0_21_health_record_deletions(connection)
    _seed_v0_21_auth_known_devices(connection)
    _seed_v0_21_follow_request_declines(connection)
    _seed_v0_21_follower_blocks(connection)
    _seed_v0_21_mfa_factors(connection)
    _seed_v0_21_oauth_states(connection)
    _seed_v0_21_users_sessions(connection)
    _seed_v0_21_rotated_refresh_tokens(connection)
    _seed_v0_21_idp_session_tokens(connection)
    _seed_v0_21_second_identity_provider(connection)
    _seed_v0_21_idp_notifications(connection)
    _seed_v0_21_activity_children(connection)
    _seed_v0_21_activity_references(connection)
    seed_events(connection, IDP_EVENT_CASES, IDP_EVENT_METADATA, IDP_EVENT_PREFIX)
    seed_events(connection, ACTIVITY_EVENT_CASES, ACTIVITY_EVENT_METADATA, ACTIVITY_EVENT_PREFIX)
