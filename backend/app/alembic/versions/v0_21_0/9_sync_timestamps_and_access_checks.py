"""Incremental sync timestamps and access checks

The steps run in this order.

Updated_at and tombstones for incremental sync
----------------------------------------------

Adds ``updated_at`` to every record ``GET /sync`` reports (activities, the health records, health targets, gear and
gear components), with an index on ``(user_id, updated_at, id)`` for the keyset walk. An existing row is stamped
with the migration's time, and an activity with its ``created_at``, so a first sync reports every record either way.

Adds the tombstone tables the owning modules write in the transaction of a delete: ``activity_deletions``,
``health_record_deletions`` (with the health record's sync type), ``gear_deletions`` and
``gear_component_deletions``, each indexed on ``(user_id, deleted_at, id)``.

Drop the unused identity provider jwks_uri
------------------------------------------

Sign-in and back-channel logout take the signing keys from the provider's discovery document, never from this
column, so the column and the field that filled it are removed.

Record the known device a session signed in from
------------------------------------------------

Forgetting a known device also signs it out, which needs each session to name the device it was opened from. The
column holds the SHA-256 hex digest of the device id, as ``known_devices`` stores it. There is no backfill: a session
that exists at the upgrade keeps null, so forgetting its device does not end it.

Drop the audit trail retention and legal hold settings
------------------------------------------------------

The audit trail is kept for the platform's default retention, with no legal hold, so ``server_settings`` no longer
stores either. The downgrade restores the columns with their defaults and the retention check constraint.

Record when an API key was revoked
----------------------------------

The purge of stale API keys needs the moment a key was revoked, which ``is_active`` alone does not hold. A key that is
already revoked at the upgrade takes the upgrade time, the latest instant it can have been revoked, so it is kept
for the full retention period before the purge and is never deleted at once because it was created long ago.

Constrain users.access_type to the two known access types
---------------------------------------------------------

Scope derivation fails closed on an access type it does not know, so the column only accepts ``regular`` and
``admin``. Every row written since revision 0.17.0 holds one of the two; the constraint creation fails on the
upgrade if a row holds anything else, rather than leaving an account no scope can be derived for.

Revision ID: b84e9f3a6c25
Revises: a77c4e8f1b26
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b84e9f3a6c25"
down_revision: str | None = "a77c4e8f1b26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each synced table and the name of its ``(user_id, updated_at, id)`` index.
_SYNCED = (
    ("activities", "ix_activities_user_id_updated_at_id"),
    ("health_weight", "ix_health_weight_user_updated_at_id"),
    ("health_steps", "ix_health_steps_user_updated_at_id"),
    ("health_sleep", "ix_health_sleep_user_updated_at_id"),
    ("health_water", "ix_health_water_user_updated_at_id"),
    ("health_poop", "ix_health_poop_user_updated_at_id"),
    ("health_fasting", "ix_health_fasting_user_updated_at_id"),
    ("health_targets", "ix_health_targets_user_updated_at_id"),
    ("gear", "ix_gear_user_id_updated_at_id"),
    ("gear_components", "ix_gear_components_user_id_updated_at_id"),
)

#: Each tombstone table, the name of its ``(user_id, deleted_at, id)`` index, and whether it names a record type.
_TOMBSTONES = (
    ("activity_deletions", "ix_activity_deletions_user_id_deleted_at_id", False),
    ("health_record_deletions", "ix_health_record_deletions_user_deleted_at_id", True),
    ("gear_deletions", "ix_gear_deletions_user_id_deleted_at_id", False),
    ("gear_component_deletions", "ix_gear_component_deletions_user_id_deleted_at_id", False),
)


def upgrade_sync_timestamps() -> None:
    """Stamp every synced table and create the tombstone tables."""
    for table, index in _SYNCED:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
                comment="When the record last changed",
            ),
        )
        op.create_index(index, table, ["user_id", "updated_at", "id"])
    # An activity has changed at least since it was recorded.
    op.execute(sa.text("UPDATE activities SET updated_at = created_at WHERE created_at IS NOT NULL"))

    for table, index, typed in _TOMBSTONES:
        columns = [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner of the deleted record"),
            sa.Column("record_id", sa.Integer(), nullable=False, comment="The id the deleted record had"),
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
                comment="When the record was deleted",
            ),
        ]
        if typed:
            columns.append(
                sa.Column("record_type", sa.String(length=50), nullable=False, comment="Sync type of the record")
            )
        op.create_table(
            table,
            *columns,
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(index, table, ["user_id", "deleted_at", "id"])


def downgrade_sync_timestamps() -> None:
    """Drop the tombstone tables and the stamps."""
    for table, index, _ in reversed(_TOMBSTONES):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
    for table, index in reversed(_SYNCED):
        op.drop_index(index, table_name=table)
        op.drop_column(table, "updated_at")


def upgrade_drop_identity_provider_jwks_uri() -> None:
    """Drop the jwks_uri column."""
    op.drop_column("identity_providers", "jwks_uri")


def downgrade_drop_identity_provider_jwks_uri() -> None:
    """Add the jwks_uri column back, empty: the dropped values are not kept."""
    op.add_column(
        "identity_providers",
        sa.Column("jwks_uri", sa.String(length=500), nullable=True, comment="OIDC JWKS URI for token verification"),
    )


def upgrade_session_device_hash() -> None:
    """Add the nullable device hash column."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "device_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex digest of the device id the session signed in from",
        ),
    )


def downgrade_session_device_hash() -> None:
    """Drop the device hash column."""
    op.drop_column("users_sessions", "device_hash")


def upgrade_drop_audit_retention_settings() -> None:
    """Drop the retention check constraint and both columns."""
    op.drop_constraint("audit_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "audit_legal_hold")
    op.drop_column("server_settings", "audit_retention_days")


def downgrade_drop_audit_retention_settings() -> None:
    """Restore both columns with their defaults and the retention check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
            comment="Days after which audit trail partitions are dropped (0 - never)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_legal_hold",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Suspend all pruning of the audit trail (true - yes, false - no)",
        ),
    )
    op.create_check_constraint(
        "audit_retention_days_check",
        "server_settings",
        "audit_retention_days = 0 OR audit_retention_days BETWEEN 30 AND 36500",
    )


def upgrade_api_key_revoked_at() -> None:
    """Add the nullable revocation time and backfill the keys already revoked."""
    op.add_column(
        "users_api_keys",
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the key was revoked; null while it has not been",
        ),
    )
    op.execute("UPDATE users_api_keys SET revoked_at = now() WHERE is_active = false")


def downgrade_api_key_revoked_at() -> None:
    """Drop the revocation time column."""
    op.drop_column("users_api_keys", "revoked_at")


_CONSTRAINT = "ck_users_access_type"


def upgrade_users_access_type_check() -> None:
    """Add the check that limits ``users.access_type`` to ``regular`` and ``admin``."""
    op.create_check_constraint(_CONSTRAINT, "users", "access_type IN ('regular', 'admin')")


def downgrade_users_access_type_check() -> None:
    """Drop the access type check."""
    op.drop_constraint(_CONSTRAINT, "users", type_="check")


def upgrade() -> None:
    """Run every step in order."""
    upgrade_sync_timestamps()
    upgrade_drop_identity_provider_jwks_uri()
    upgrade_session_device_hash()
    upgrade_drop_audit_retention_settings()
    upgrade_api_key_revoked_at()
    upgrade_users_access_type_check()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_users_access_type_check()
    downgrade_api_key_revoked_at()
    downgrade_drop_audit_retention_settings()
    downgrade_session_device_hash()
    downgrade_drop_identity_provider_jwks_uri()
    downgrade_sync_timestamps()
