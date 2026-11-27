"""Uniqueness constraints, row versions and server settings

The steps run in this order. The three gear steps are skipped on a database that already has them: v0.21.0 committed
them on their own, so an upgrade it did not finish left them in place without recording this revision.

Enforce gear nickname uniqueness per user
-----------------------------------------

Add the gear and gear component optimistic-concurrency version columns
----------------------------------------------------------------------

Scope the provider gear IDs to the user
---------------------------------------

Index notifications by user and creation date
---------------------------------------------

The notifications list is read per user, newest first. The composite index serves
that ordering and covers the lookups the single ``user_id`` index served, so it is
dropped. A partial index on the creation date of read rows serves the daily retention
purge, which would otherwise scan the table for every batch.

The indexes are built in the migration transaction, so a failed upgrade rolls back whole; writes to
``notifications`` wait until the upgrade commits. An index of either name that already exists is rebuilt,
because a build v0.21.0 did not finish leaves an invalid index behind.

Store the mail server settings in the database
----------------------------------------------

Creates the singleton ``mail_settings`` table the admin UI edits, with its row
inserted so every install has one. Mail starts disabled (no host); an install that
sets the ``SMTP_*`` variables has them imported on the next API start.

Store the reverse-geocoding settings in the database
----------------------------------------------------

Adds the geocoding columns to ``server_settings``. The server defaults reproduce the
behaviour of an install without the ``REVERSE_GEO_*`` variables (Nominatim over HTTPS,
one request per second); an install that sets them has them imported on the next API start.

Store the session and token policy in the database
--------------------------------------------------

Adds the session timeout and token lifetime columns to ``server_settings``. The server
defaults equal the defaults of the ``SESSION_*``, ``ACCESS_TOKEN_EXPIRE_MINUTES`` and
``REFRESH_TOKEN_EXPIRE_DAYS`` variables; an install that sets them has them imported on
the next API start.

Store the read-notification retention in the database
-----------------------------------------------------

Adds ``read_notification_retention_days`` to ``server_settings``. The server default equals
the default of ``READ_NOTIFICATION_RETENTION_DAYS``; an install that sets it has it imported
on the next API start.

Add an optimistic-concurrency version to the settings rows
----------------------------------------------------------

Adds ``version`` to ``server_settings`` and ``mail_settings`` so an admin whose form is stale is
refused instead of silently reverting another admin's change.

Enforce the settings rules the application relies on
----------------------------------------------------

The absolute session timeout is never below the idle timeout, and the geocoding rate limit is
within the range the settings schema accepts, so a row written without going through the schema
cannot break every read of the settings.

One health record per user and day
----------------------------------

Steps, weight, sleep and water are one record per user and day. The services look for the
day's record before creating one, which is read-then-write: two requests, or a request
beside a Garmin Connect sync on another replica, can both see "not found" and both insert.
The guarantee moves into the database as a unique ``(user_id, date)`` constraint.

Existing duplicates are merged first. The newest row of a day (highest id) is kept; water is
cumulative, so the kept row takes the day's total.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it
builds. The tables hold at most one row per user and day, so that is brief.

One default-gear row per user
-----------------------------

A user has one set of default gear. The rows are created on demand by a read-then-write, so two
requests can both see "not found" and both insert; the user then has two rows and every lookup
that expects one fails for good. The guarantee moves into the database as a unique ``user_id``.

Existing duplicates are removed first, keeping the newest row (highest id) of each user. The row
holds only references to gear, so nothing else points at it.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it
builds. The table holds one row per user, so that is brief.

One in-progress fast per user
-----------------------------

A user has at most one running fast. The service looks for one before starting another, which is a
read-then-write, so two requests can both see "none" and both insert; the user then has two running
fasts and every lookup of the active one fails for good. The guarantee moves into the database as a
unique index on ``user_id`` over the in-progress rows.

Existing duplicates are resolved first: the most recently started fast of each user keeps running and
the older ones are cancelled, which keeps their rows and their start times.

The index is not built ``CONCURRENTLY``, so it blocks writes to the table while it builds. The table
holds one row per fast, so that is brief.

Add an optimistic-concurrency version to the health tables
----------------------------------------------------------

Adds ``version`` to every health table so a client whose copy is stale is refused instead of
silently reverting another client's change. The column starts at 1 on existing rows.

Add an optimistic-concurrency version to the users tables
---------------------------------------------------------

Adds ``version`` to ``users`` and the per-user settings tables an edit form reads and writes, so a
client whose copy is stale is refused instead of silently reverting another client's change. The
column starts at 1 on existing rows.

Revision ID: a8d3e5c1f7b2
Revises: c5cfe02a11c2
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
import logging

# revision identifiers, used by Alembic.
revision: str = "a8d3e5c1f7b2"
down_revision: str | None = "c5cfe02a11c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAME_DUPLICATES = """
    UPDATE gear
    SET nickname = left(gear.nickname, 250 - length(' (' || gear.id || ')')) || ' (' || gear.id || ')'
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY user_id, lower(nickname) ORDER BY id) AS row_position
        FROM gear
    ) ranked
    WHERE gear.id = ranked.id AND ranked.row_position > 1
"""

_HAS_DUPLICATES = "SELECT 1 FROM gear GROUP BY user_id, lower(nickname) HAVING count(*) > 1 LIMIT 1"

# Each pass appends a distinct id, so a handful of passes always settles.
_MAX_RENAME_PASSES = 5


def upgrade_gear_nickname_unique_per_user() -> None:
    connection = op.get_bind()
    op.execute("UPDATE gear SET nickname = btrim(nickname) WHERE nickname <> btrim(nickname)")
    for _ in range(_MAX_RENAME_PASSES):
        op.execute(_RENAME_DUPLICATES)
        if connection.exec_driver_sql(_HAS_DUPLICATES).first() is None:
            break
    op.execute("DROP INDEX IF EXISTS ix_gear_nickname")
    op.execute("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, lower(nickname))")


def downgrade_gear_nickname_unique_per_user() -> None:
    op.execute("DROP INDEX IF EXISTS uq_gear_user_nickname")
    op.execute("CREATE INDEX IF NOT EXISTS ix_gear_nickname ON gear (nickname)")


_GEAR_VERSION_TABLES = ("gear", "gear_components")


def upgrade_gear_version() -> None:
    """Add the version counter backing ETag/If-Match on gears and their components."""
    for table in _GEAR_VERSION_TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade_gear_version() -> None:
    """Remove the version counters."""
    for table in reversed(_GEAR_VERSION_TABLES):
        op.drop_column(table, "version")


_COLUMNS = {
    "strava_gear_id": "uq_gear_user_strava_gear_id",
    "garminconnect_gear_id": "uq_gear_user_garminconnect_gear_id",
}


def upgrade_gear_provider_ids_unique_per_user() -> None:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("gear"):
        if len(constraint["column_names"]) == 1 and constraint["column_names"][0] in _COLUMNS:
            op.drop_constraint(constraint["name"], "gear", type_="unique")
    for column, name in _COLUMNS.items():
        op.create_unique_constraint(name, "gear", ["user_id", column])


def downgrade_gear_provider_ids_unique_per_user() -> None:
    for column, name in _COLUMNS.items():
        op.drop_constraint(name, "gear", type_="unique")
        # Two users may now hold the same provider ID; the table-wide constraint allows one
        # owner, so every later holder loses the link rather than blocking the downgrade.
        op.execute(
            f"UPDATE gear SET {column} = NULL WHERE {column} IS NOT NULL AND id NOT IN "  # noqa: S608 - column is from _COLUMNS
            f"(SELECT min(id) FROM gear WHERE {column} IS NOT NULL GROUP BY {column})"
        )
        op.create_unique_constraint(None, "gear", [column])


def upgrade_notifications_user_created_index() -> None:
    """Swap the user index for the user and creation date index and add the purge index."""
    for name in ("ix_notifications_user_id_created_at", "ix_notifications_read_created_at", "ix_notifications_user_id"):
        op.drop_index(name, table_name="notifications", if_exists=True)
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_read_created_at", "notifications", ["created_at"], postgresql_where=sa.text("read")
    )


def downgrade_notifications_user_created_index() -> None:
    """Restore the single-column user index."""
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.drop_index("ix_notifications_read_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")


def upgrade_add_mail_settings() -> None:
    """Create the mail_settings table and its singleton row."""
    op.create_table(
        "mail_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=True, comment="Mail server hostname (NULL - mail disabled)"),
        sa.Column("port", sa.Integer(), server_default=sa.text("587"), nullable=False, comment="Mail server port"),
        sa.Column(
            "security",
            sa.String(length=10),
            server_default="starttls",
            nullable=False,
            comment="Connection security (starttls, ssl, none)",
        ),
        sa.Column("username", sa.String(length=320), nullable=True, comment="Mail server authentication username"),
        sa.Column(
            "password",
            sa.String(length=512),
            nullable=True,
            comment="Mail server authentication password (encrypted)",
        ),
        sa.Column(
            "from_address",
            sa.String(length=320),
            nullable=True,
            comment="Sender address (NULL - the username is used)",
        ),
        sa.CheckConstraint("id = 1", name="mail_settings_single_row_check"),
        sa.CheckConstraint("security IN ('starttls', 'ssl', 'none')", name="mail_settings_security_check"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO mail_settings (id) VALUES (1)"))


def downgrade_add_mail_settings() -> None:
    """Drop the mail_settings table."""
    op.drop_table("mail_settings")


def upgrade_add_geocoding_settings() -> None:
    """Add the geocoding columns and the service check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_service",
            sa.String(length=20),
            server_default="nominatim",
            nullable=False,
            comment="Reverse-geocoding service (nominatim, photon, geocode)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_host",
            sa.String(length=253),
            nullable=True,
            comment="Host of the geocoding service (NULL - the service's default host)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_use_https",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="Address the geocoding host over HTTPS (true - yes, false - no)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_rate_limit",
            sa.Float(),
            server_default=sa.text("1.0"),
            nullable=False,
            comment="Maximum geocoding requests per second (0 disables throttling)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_api_key",
            sa.String(length=512),
            nullable=True,
            comment="API key encrypted for the geocoding service",
        ),
    )
    op.create_check_constraint(
        "geocoding_service_check",
        "server_settings",
        "geocoding_service IN ('nominatim', 'photon', 'geocode')",
    )


def downgrade_add_geocoding_settings() -> None:
    """Drop the geocoding columns."""
    op.drop_constraint("geocoding_service_check", "server_settings", type_="check")
    op.drop_column("server_settings", "geocoding_api_key")
    op.drop_column("server_settings", "geocoding_rate_limit")
    op.drop_column("server_settings", "geocoding_use_https")
    op.drop_column("server_settings", "geocoding_host")
    op.drop_column("server_settings", "geocoding_service")


_BOUNDED_COLUMNS: tuple[tuple[str, int, str, int, str], ...] = (
    ("session_idle_timeout_hours", 1, "Hours of inactivity after which a session ends", 8760, "1"),
    ("session_absolute_timeout_hours", 24, "Hours after which a session ends whatever its activity", 8760, "1"),
    ("access_token_expire_minutes", 15, "Access token lifetime in minutes", 1440, "1"),
    ("refresh_token_expire_days", 7, "Refresh token lifetime in days", 365, "1"),
)


def upgrade_add_session_policy() -> None:
    """Add the session policy columns and their range check constraints."""
    op.add_column(
        "server_settings",
        sa.Column(
            "session_idle_timeout_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Enforce session idle and absolute timeouts (true - yes, false - no)",
        ),
    )
    for name, default, comment, upper, lower in _BOUNDED_COLUMNS:
        op.add_column(
            "server_settings",
            sa.Column(name, sa.Integer(), server_default=sa.text(str(default)), nullable=False, comment=comment),
        )
        op.create_check_constraint(f"{name}_check", "server_settings", f"{name} BETWEEN {lower} AND {upper}")


def downgrade_add_session_policy() -> None:
    """Drop the session policy columns."""
    for name, *_ in reversed(_BOUNDED_COLUMNS):
        op.drop_constraint(f"{name}_check", "server_settings", type_="check")
        op.drop_column("server_settings", name)
    op.drop_column("server_settings", "session_idle_timeout_enabled")


def upgrade_add_notification_retention() -> None:
    """Add the retention column and its range check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "read_notification_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
            comment="Days after which read notifications are purged (0 - never)",
        ),
    )
    op.create_check_constraint(
        "read_notification_retention_days_check",
        "server_settings",
        "read_notification_retention_days BETWEEN 0 AND 3650",
    )


def downgrade_add_notification_retention() -> None:
    """Drop the retention column."""
    op.drop_constraint("read_notification_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "read_notification_retention_days")


_SETTINGS_VERSION_TABLES = ("server_settings", "mail_settings")


def upgrade_settings_version() -> None:
    """Add the version column to both settings tables."""
    for table in _SETTINGS_VERSION_TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade_settings_version() -> None:
    """Drop the version column from both settings tables."""
    for table in _SETTINGS_VERSION_TABLES:
        op.drop_column(table, "version")


def upgrade_settings_consistency_checks() -> None:
    """Add the two check constraints."""
    op.create_check_constraint(
        "session_absolute_not_below_idle_check",
        "server_settings",
        "session_absolute_timeout_hours >= session_idle_timeout_hours",
    )
    op.create_check_constraint(
        "geocoding_rate_limit_check", "server_settings", "geocoding_rate_limit BETWEEN 0 AND 100"
    )


def downgrade_settings_consistency_checks() -> None:
    """Drop the two check constraints."""
    op.drop_constraint("geocoding_rate_limit_check", "server_settings", type_="check")
    op.drop_constraint("session_absolute_not_below_idle_check", "server_settings", type_="check")


logger = logging.getLogger("alembic.runtime.migration")

_HEALTH_ONE_RECORD_PER_DAY_TABLES = ("health_steps", "health_weight", "health_sleep", "health_water")

_SUM_WATER = """
    UPDATE health_water
    SET amount_ml = totals.total
    FROM (
        SELECT max(id) AS keep_id, sum(amount_ml) AS total
        FROM health_water
        GROUP BY user_id, date
        HAVING count(*) > 1
    ) totals
    WHERE health_water.id = totals.keep_id
"""

_HEALTH_ONE_RECORD_PER_DAY_KEEP_NEWEST = (
    "DELETE FROM {table} WHERE id NOT IN (SELECT max(id) FROM {table} GROUP BY user_id, date)"
)


def upgrade_health_one_record_per_day() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(_SUM_WATER))
    for table in _HEALTH_ONE_RECORD_PER_DAY_TABLES:
        removed = bind.execute(sa.text(_HEALTH_ONE_RECORD_PER_DAY_KEEP_NEWEST.format(table=table))).rowcount
        if removed:
            # The older rows of a day are not recoverable afterwards, so say how many went.
            logger.warning("Removed %d duplicate %s rows, keeping the newest of each day", removed, table)
        op.create_unique_constraint(f"uq_{table}_user_date", table, ["user_id", "date"])


def downgrade_health_one_record_per_day() -> None:
    for table in _HEALTH_ONE_RECORD_PER_DAY_TABLES:
        op.drop_constraint(f"uq_{table}_user_date", table, type_="unique")


_USERS_DEFAULT_GEAR_ONE_PER_USER_KEEP_NEWEST = (
    "DELETE FROM users_default_gear WHERE id NOT IN (SELECT max(id) FROM users_default_gear GROUP BY user_id)"
)


def upgrade_users_default_gear_one_per_user() -> None:
    op.execute(_USERS_DEFAULT_GEAR_ONE_PER_USER_KEEP_NEWEST)
    op.create_unique_constraint("uq_users_default_gear_user_id", "users_default_gear", ["user_id"])


def downgrade_users_default_gear_one_per_user() -> None:
    op.drop_constraint("uq_users_default_gear_user_id", "users_default_gear", type_="unique")


_INDEX = "uq_health_fasting_one_in_progress_per_user"

_IN_PROGRESS = "status = 'in_progress'"

_CANCEL_OLDER = """
UPDATE health_fasting SET status = 'cancelled'
WHERE status = 'in_progress'
  AND id NOT IN (
    SELECT DISTINCT ON (user_id) id FROM health_fasting
    WHERE status = 'in_progress'
    ORDER BY user_id, fast_start_time DESC, id DESC
  )
"""


def upgrade_health_fasting_one_in_progress() -> None:
    op.execute(_CANCEL_OLDER)
    op.create_index(_INDEX, "health_fasting", ["user_id"], unique=True, postgresql_where=sa.text(_IN_PROGRESS))


def downgrade_health_fasting_one_in_progress() -> None:
    op.drop_index(_INDEX, table_name="health_fasting")


_HEALTH_VERSION_TABLES = (
    "health_weight",
    "health_water",
    "health_steps",
    "health_sleep",
    "health_poop",
    "health_fasting",
    "health_targets",
)


def upgrade_health_version() -> None:
    """Add the version column to every health table."""
    for table in _HEALTH_VERSION_TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade_health_version() -> None:
    """Drop the version column from every health table."""
    for table in _HEALTH_VERSION_TABLES:
        op.drop_column(table, "version")


_USERS_VERSION_TABLES = ("users", "users_privacy_settings", "users_default_gear", "users_goals")


def upgrade_users_version() -> None:
    """Add the version column to each table."""
    for table in _USERS_VERSION_TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade_users_version() -> None:
    """Drop the version column from each table."""
    for table in _USERS_VERSION_TABLES:
        op.drop_column(table, "version")


def _has_committed_gear_steps() -> bool:
    """Whether the gear steps are already applied; they are committed together, so the version column shows it."""
    return any(column["name"] == "version" for column in sa.inspect(op.get_bind()).get_columns("gear"))


def upgrade() -> None:
    """Run every step in order, leaving out the gear steps a database already has."""
    if not _has_committed_gear_steps():
        upgrade_gear_nickname_unique_per_user()
        upgrade_gear_version()
        upgrade_gear_provider_ids_unique_per_user()
    upgrade_notifications_user_created_index()
    upgrade_add_mail_settings()
    upgrade_add_geocoding_settings()
    upgrade_add_session_policy()
    upgrade_add_notification_retention()
    upgrade_settings_version()
    upgrade_settings_consistency_checks()
    upgrade_health_one_record_per_day()
    upgrade_users_default_gear_one_per_user()
    upgrade_health_fasting_one_in_progress()
    upgrade_health_version()
    upgrade_users_version()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_users_version()
    downgrade_health_version()
    downgrade_health_fasting_one_in_progress()
    downgrade_users_default_gear_one_per_user()
    downgrade_health_one_record_per_day()
    downgrade_settings_consistency_checks()
    downgrade_settings_version()
    downgrade_add_notification_retention()
    downgrade_add_session_policy()
    downgrade_add_geocoding_settings()
    downgrade_add_mail_settings()
    downgrade_notifications_user_created_index()
    downgrade_gear_provider_ids_unique_per_user()
    downgrade_gear_version()
    downgrade_gear_nickname_unique_per_user()
