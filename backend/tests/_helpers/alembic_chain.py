"""Helpers that run the application's real Alembic chain against a disposable PostgreSQL database."""

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


def _execute(connection: Connection, statement: str, **params: str) -> None:
    """Run one static INSERT, passing JSON documents as bound parameters."""
    connection.execute(sa.text(statement), params)


def _seed_users(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO users (id, name, username, email, preferred_language, email_verified, pending_admin_approval,
               active, gender, access_type, first_day_of_week, units, currency)
           VALUES (1, 'Admin User', 'admin', 'admin@example.com', 'en', true, false, true, 'male', 'admin',
               'monday', 'metric', 'euro'),
               (2, 'Regular User', 'regular', 'regular@example.com', 'en', true, false, true, 'female', 'regular',
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
    _execute(
        connection,
        "INSERT INTO users_goals (id, user_id, interval, goal_distance, activity_type, goal_type) "
        "VALUES (1, 1, 'weekly', 50000, 'run', 'distance')",
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
           VALUES ('seed-reset-token', 1, 'seed-reset-hash', '2024-05-01 10:00:00', '2030-01-01 00:00:00', false)""",
    )


def _seed_sign_up_tokens(connection: Connection) -> None:
    _execute(
        connection,
        """INSERT INTO sign_up_tokens (id, user_id, token_hash, created_at, expires_at, used)
           VALUES ('seed-signup-token', 2, 'seed-signup-hash', '2024-05-01 10:00:00', '2030-01-01 00:00:00',
               false)""",
    )


def _seed_followers(connection: Connection) -> None:
    _execute(connection, "INSERT INTO followers (id, follower_id, followee_id, status) VALUES (1, 2, 1, 'accepted')")


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

    The statements are written against the v0.20 head shape and run in dependency order: users first, then what
    refers to them, then the activities and the substrate tables. ``server_settings`` and ``migrations`` are filled
    by the chain itself. Commits are the caller's.

    Args:
        connection: A connection on a database at ``V0_20_HEAD``.
    """
    _seed_users(connection)
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
    _execute(connection, "INSERT INTO follower_blocks (id, blocker_id, blocked_id) VALUES (1, 1, 2)")


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
    _seed_v0_21_health_record_deletions(connection)
    _seed_v0_21_auth_known_devices(connection)
    _seed_v0_21_follow_request_declines(connection)
    _seed_v0_21_follower_blocks(connection)
    _seed_v0_21_mfa_factors(connection)
    _seed_v0_21_oauth_states(connection)
    _seed_v0_21_users_sessions(connection)
    _seed_v0_21_rotated_refresh_tokens(connection)
    _seed_v0_21_idp_session_tokens(connection)
