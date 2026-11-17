"""Gear, health, API key and identity provider session schema

The steps run in this order.

Store the day a gear was acquired as a date
-------------------------------------------

``gear.created_at`` was never a server timestamp: the gear form asks the user for the date they acquired the
gear and stores what they pick. The column is renamed ``acquired_on`` and becomes a ``DATE``; each row keeps
the UTC calendar day of its stored value. A gear created without a date gets the current date.

The downgrade turns each date back into a timestamp at midnight UTC.

Let a user opt out of the username search
-----------------------------------------

``users_privacy_settings.discoverable`` is the "let others find me in search" switch. Every existing row keeps
appearing in search, so the column is added switched on.

Cap the lifetime of API keys
----------------------------

Adds ``api_key_max_lifetime_days`` to ``server_settings`` and gives every API key that never expires an
expiry of 365 days from now, the setting's default, whatever the setting is. A key that already has an
expiry, including one in the past, is left as it is. ``users_api_keys.expires_at`` is then required.

Drop the identity-provider link tokens
--------------------------------------

Linking an identity provider now starts from an authenticated ``POST``, so the one-time link tokens and their
table are gone. The downgrade recreates the empty table.

Record when Strava access was revoked
-------------------------------------

``users_integrations.strava_revoked_at`` marks the moment Strava refused the user's refresh token. A
recurring job deletes the user's Strava API data once the grace period after it has passed, unless the
user relinks first.

Keep identity-provider tokens per session
-----------------------------------------

Each Endurain session that signed in through an identity provider now has a row in ``idp_session_tokens``,
holding the refresh token that sign-in was issued, so a session is refreshed and revoked at the provider on
its own. The link's three token columns are dropped: a token stored there cannot be tied to a session and is
discarded, and the sessions open today keep working until they expire, without identity-provider refresh. The
downgrade restores the empty columns and drops the table.

Mark sessions that already hold a refresh token as exchanged
------------------------------------------------------------

A password sign-in creates its session with the refresh token, so it needs no token exchange, yet the
session was stored with ``tokens_exchanged`` false. Session lists now hide sessions whose exchange has not
happened, so those rows are marked exchanged.

Every health record has a source, ``manual`` by default
-------------------------------------------------------

Weight, steps, sleep and water stored ``NULL`` for a record a person entered, while poop and fasting stored
``manual``. The six ``source`` columns are now ``NOT NULL`` with the server default ``manual``. A ``NULL`` becomes
``manual``, except a sleep record that carries a Garmin Connect sleep id, which is ``garmin``.

Put the unit in the name of the health columns
----------------------------------------------

Weight, body composition, sleep oxygen saturation and the health targets named their unit only in a comment.
The wire names now carry it (``weight_kg``, ``body_fat_percent``, ``sleep_seconds``), and the columns are
renamed so the ORM and the API agree. The values are unchanged.

Store a gear's initial distance in meters
-----------------------------------------

``gear.initial_kms`` held kilometers while the gear's usage (``total_distance``) is in meters. The column becomes
``initial_distance`` in meters and is widened to ``Numeric(14, 2)`` so the converted values fit.

Add follower_blocks and follow_request_declines
-----------------------------------------------

``follower_blocks`` holds each user's block list: a blocked user cannot request to follow the blocker.
``follow_request_declines`` holds when a follow request was last declined, since declining deletes the request, so the
requester can be refused for seven days. Both tables start empty.

Rename gear_components.expected_kms to expected_usage
-----------------------------------------------------

The column holds the wear threshold in meters for a distance-tracked gear and in seconds for a time-tracked one, so
its name no longer says kilometers. The values are unchanged.

Revision ID: f1b6d3a8c254
Revises: f2c6a9d4b871
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1b6d3a8c254"
down_revision: str | None = "f2c6a9d4b871"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade_gear_acquired_on() -> None:
    """Rename the column, convert it to its UTC calendar day and default new rows to today."""
    op.execute("ALTER TABLE gear RENAME COLUMN created_at TO acquired_on")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on DROP DEFAULT")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on TYPE date USING (acquired_on AT TIME ZONE 'UTC')::date")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on SET DEFAULT CURRENT_DATE")
    op.execute("COMMENT ON COLUMN gear.acquired_on IS 'Date the user acquired the gear (today when not given)'")


def downgrade_gear_acquired_on() -> None:
    """Rename the column back and turn each date into midnight UTC."""
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on DROP DEFAULT")
    op.execute(
        "ALTER TABLE gear ALTER COLUMN acquired_on TYPE timestamptz USING acquired_on::timestamp AT TIME ZONE 'UTC'"
    )
    op.execute("ALTER TABLE gear RENAME COLUMN acquired_on TO created_at")
    op.execute("COMMENT ON COLUMN gear.created_at IS 'Gear creation date (DateTime)'")


def upgrade_privacy_discoverable() -> None:
    """Add the column, switched on for every existing row."""
    op.add_column(
        "users_privacy_settings",
        sa.Column(
            "discoverable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Appear in other users' username search",
        ),
    )


def downgrade_privacy_discoverable() -> None:
    """Drop the column."""
    op.drop_column("users_privacy_settings", "discoverable")


def upgrade_api_key_max_lifetime() -> None:
    """Add the setting, backfill the keys that never expire and require an expiry."""
    op.add_column(
        "server_settings",
        sa.Column(
            "api_key_max_lifetime_days",
            sa.Integer(),
            server_default=sa.text("365"),
            nullable=False,
            comment="Longest lifetime of a new API key, and its default, in days",
        ),
    )
    op.create_check_constraint(
        "api_key_max_lifetime_days_check", "server_settings", "api_key_max_lifetime_days BETWEEN 1 AND 3650"
    )
    op.execute("UPDATE users_api_keys SET expires_at = now() + interval '365 days' WHERE expires_at IS NULL")
    op.alter_column(
        "users_api_keys",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_comment="Key expiration timestamp (NULL = no expiry)",
        comment="Key expiration timestamp",
    )


def downgrade_api_key_max_lifetime() -> None:
    """Allow keys without an expiry again and drop the setting."""
    op.alter_column(
        "users_api_keys",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_comment="Key expiration timestamp",
        comment="Key expiration timestamp (NULL = no expiry)",
    )
    op.drop_constraint("api_key_max_lifetime_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "api_key_max_lifetime_days")


def upgrade_drop_idp_link_tokens() -> None:
    """Drop the link-token table and its indexes."""
    op.drop_index(op.f("ix_idp_link_tokens_user_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_token_hash"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_idp_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_expires_at"), table_name="idp_link_tokens")
    op.drop_table("idp_link_tokens")


def downgrade_drop_idp_link_tokens() -> None:
    """Recreate the empty link-token table with its indexes."""
    op.create_table(
        "idp_link_tokens",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Opaque row identifier, not the link token"),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hash of the one-time link token",
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID linking the identity provider"),
        sa.Column("idp_id", sa.Integer(), nullable=False, comment="Identity provider ID being linked"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Token creation timestamp",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Token expiry at 60 seconds (cleanup marker)",
        ),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            comment="Single-use flag (False - unused, True - used)",
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True, comment="Client IP address (IPv6 max length)"),
        sa.ForeignKeyConstraint(["idp_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_idp_link_tokens_expires_at"), "idp_link_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_id"), "idp_link_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_idp_id"), "idp_link_tokens", ["idp_id"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_token_hash"), "idp_link_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_idp_link_tokens_user_id"), "idp_link_tokens", ["user_id"], unique=False)


def upgrade_strava_revoked_at() -> None:
    """Add the nullable revocation timestamp."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "strava_revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When Strava refused the refresh token; Strava data is deleted after the grace period",
        ),
    )


def downgrade_strava_revoked_at() -> None:
    """Drop the revocation timestamp."""
    op.drop_column("users_integrations", "strava_revoked_at")


_TABLE = "idp_session_tokens"

_LINKS = "users_identity_providers"

_IDP_INDEX = "ix_idp_session_tokens_idp_id"

_USER_INDEX = "ix_idp_session_tokens_user_id"


def upgrade_idp_session_tokens() -> None:
    """Create the per-session token table and drop the link's token columns."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=False,
            comment="Endurain session the sign-in created; no foreign key, so the token outlives the session row",
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID"),
        sa.Column("idp_id", sa.Integer(), nullable=False, comment="Identity Provider ID"),
        sa.Column("refresh_token", sa.Text(), nullable=True, comment="Encrypted refresh token"),
        sa.Column(
            "access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Access token expiry time",
        ),
        sa.Column(
            "refresh_token_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last refresh token update",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the session signed in through the provider",
        ),
        sa.ForeignKeyConstraint(["idp_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(_IDP_INDEX, _TABLE, ["idp_id"], unique=False)
    op.create_index(_USER_INDEX, _TABLE, ["user_id"], unique=False)
    op.drop_column(_LINKS, "idp_refresh_token_updated_at")
    op.drop_column(_LINKS, "idp_access_token_expires_at")
    op.drop_column(_LINKS, "idp_refresh_token")


def downgrade_idp_session_tokens() -> None:
    """Restore the link's empty token columns and drop the per-session token table."""
    op.add_column(_LINKS, sa.Column("idp_refresh_token", sa.Text(), nullable=True, comment="Encrypted refresh token"))
    op.add_column(
        _LINKS,
        sa.Column(
            "idp_access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Access token expiry time",
        ),
    )
    op.add_column(
        _LINKS,
        sa.Column(
            "idp_refresh_token_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last refresh token update",
        ),
    )
    op.drop_index(_USER_INDEX, table_name=_TABLE)
    op.drop_index(_IDP_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)


def upgrade_session_tokens_exchanged_backfill() -> None:
    """Mark every session that holds a refresh token as exchanged."""
    op.execute(
        "UPDATE users_sessions SET tokens_exchanged = true WHERE refresh_token IS NOT NULL AND tokens_exchanged = false"
    )


def downgrade_session_tokens_exchanged_backfill() -> None:
    """Leave the rows as they are: whether a session was once unexchanged cannot be recovered."""


_TABLES = ("health_weight", "health_steps", "health_sleep", "health_water", "health_poop", "health_fasting")


def _length(table: str) -> int:
    """Return the length of the table's ``source`` column."""
    return 20 if table == "health_fasting" else 250


def upgrade_health_source_manual_default() -> None:
    """Give a source to every record without one, then require it."""
    op.execute("UPDATE health_sleep SET source = 'garmin' WHERE source IS NULL AND garminconnect_sleep_id IS NOT NULL")
    for table in _TABLES:
        record = sa.table(table, sa.column("source", sa.String))
        op.execute(sa.update(record).where(record.c.source.is_(None)).values(source="manual"))
        op.alter_column(
            table,
            "source",
            existing_type=sa.String(length=_length(table)),
            nullable=False,
            server_default="manual",
        )


def downgrade_health_source_manual_default() -> None:
    """Allow a missing source again; the values stay as they are."""
    for table in _TABLES:
        op.alter_column(
            table,
            "source",
            existing_type=sa.String(length=_length(table)),
            nullable=True,
            server_default=None,
        )


#: ``(table, old name, new name, new comment)`` for every renamed column.
_RENAMES = (
    ("health_weight", "weight", "weight_kg", "Weight in kg"),
    ("health_weight", "body_fat", "body_fat_percent", "Body fat percentage"),
    ("health_weight", "body_water", "body_water_percent", "Body hydration percentage"),
    ("health_weight", "bone_mass", "bone_mass_kg", "Bone mass in kg"),
    ("health_weight", "muscle_mass", "muscle_mass_kg", "Muscle mass in kg"),
    ("health_targets", "weight", "weight_kg", "Weight in kg"),
    ("health_targets", "sleep", "sleep_seconds", "Target sleep duration in seconds"),
    ("health_targets", "fasting", "fasting_seconds", "Target fasting duration in seconds"),
    ("health_sleep", "avg_spo2", "avg_spo2_percent", "Average SpO2 oxygen saturation percentage"),
    ("health_sleep", "lowest_spo2", "lowest_spo2_percent", "Lowest SpO2 reading during sleep"),
    ("health_sleep", "highest_spo2", "highest_spo2_percent", "Highest SpO2 reading during sleep"),
)


def upgrade_health_units_in_column_names() -> None:
    """Rename the columns."""
    for table, old, new, comment in _RENAMES:
        op.alter_column(table, old, new_column_name=new, comment=comment)


def downgrade_health_units_in_column_names() -> None:
    """Restore the old column names; the comments keep their new wording."""
    for table, old, new, comment in _RENAMES:
        op.alter_column(table, new, new_column_name=old, comment=comment)


def upgrade_gear_initial_distance_meters() -> None:
    """Widen the column, convert kilometers to meters and rename it."""
    op.alter_column(
        "gear",
        "initial_kms",
        existing_type=sa.Numeric(precision=11, scale=2),
        type_=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
    )
    op.execute("UPDATE gear SET initial_kms = initial_kms * 1000")
    op.alter_column(
        "gear",
        "initial_kms",
        new_column_name="initial_distance",
        existing_type=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
        comment="Distance of the gear before it was tracked, in meters",
    )


def downgrade_gear_initial_distance_meters() -> None:
    """Rename the column back, convert meters to kilometers and narrow it."""
    op.alter_column(
        "gear",
        "initial_distance",
        new_column_name="initial_kms",
        existing_type=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
        comment="Initial kilometers of the gear",
    )
    op.execute("UPDATE gear SET initial_kms = initial_kms / 1000")
    op.alter_column(
        "gear",
        "initial_kms",
        existing_type=sa.Numeric(precision=14, scale=2),
        type_=sa.Numeric(precision=11, scale=2),
        existing_nullable=False,
    )


def upgrade_follower_blocks_and_declines() -> None:
    """Create the two tables with their unique pairs and the indexes the lookups use."""
    op.create_table(
        "follower_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False, comment="ID of the user who blocked"),
        sa.Column("blocked_id", sa.Integer(), nullable=False, comment="ID of the user who is blocked"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_follower_blocks_not_self"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_follower_blocks_blocker_blocked"),
    )
    op.create_index("ix_follower_blocks_id", "follower_blocks", ["id"], unique=False)
    op.create_index("ix_follower_blocks_blocker_id", "follower_blocks", ["blocker_id"], unique=False)
    op.create_index("ix_follower_blocks_blocked_id", "follower_blocks", ["blocked_id"], unique=False)

    op.create_table(
        "follow_request_declines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "follower_id", sa.Integer(), nullable=False, comment="ID of the requester whose request was declined"
        ),
        sa.Column("followee_id", sa.Integer(), nullable=False, comment="ID of the user who declined the request"),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=False, comment="When the request was declined"),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "followee_id", name="uq_follow_request_declines_follower_followee"),
    )
    op.create_index("ix_follow_request_declines_follower_id", "follow_request_declines", ["follower_id"], unique=False)
    op.create_index("ix_follow_request_declines_followee_id", "follow_request_declines", ["followee_id"], unique=False)


def downgrade_follower_blocks_and_declines() -> None:
    """Drop both tables, with the blocks and declines they hold."""
    op.drop_index("ix_follow_request_declines_followee_id", table_name="follow_request_declines")
    op.drop_index("ix_follow_request_declines_follower_id", table_name="follow_request_declines")
    op.drop_table("follow_request_declines")
    op.drop_index("ix_follower_blocks_blocked_id", table_name="follower_blocks")
    op.drop_index("ix_follower_blocks_blocker_id", table_name="follower_blocks")
    op.drop_index("ix_follower_blocks_id", table_name="follower_blocks")
    op.drop_table("follower_blocks")


def upgrade_gear_component_expected_usage() -> None:
    """Rename the column and describe its units."""
    op.alter_column(
        "gear_components",
        "expected_kms",
        new_column_name="expected_usage",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=(
            "Wear threshold of the gear component: meters for a distance-tracked gear, seconds for a time-tracked one"
        ),
    )


def downgrade_gear_component_expected_usage() -> None:
    """Rename the column back."""
    op.alter_column(
        "gear_components",
        "expected_usage",
        new_column_name="expected_kms",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment="Expected kilometers of the gear component",
    )


def upgrade() -> None:
    """Run every step in order."""
    upgrade_gear_acquired_on()
    upgrade_privacy_discoverable()
    upgrade_api_key_max_lifetime()
    upgrade_drop_idp_link_tokens()
    upgrade_strava_revoked_at()
    upgrade_idp_session_tokens()
    upgrade_session_tokens_exchanged_backfill()
    upgrade_health_source_manual_default()
    upgrade_health_units_in_column_names()
    upgrade_gear_initial_distance_meters()
    upgrade_follower_blocks_and_declines()
    upgrade_gear_component_expected_usage()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_gear_component_expected_usage()
    downgrade_follower_blocks_and_declines()
    downgrade_gear_initial_distance_meters()
    downgrade_health_units_in_column_names()
    downgrade_health_source_manual_default()
    downgrade_session_tokens_exchanged_backfill()
    downgrade_idp_session_tokens()
    downgrade_strava_revoked_at()
    downgrade_drop_idp_link_tokens()
    downgrade_api_key_max_lifetime()
    downgrade_privacy_discoverable()
    downgrade_gear_acquired_on()
