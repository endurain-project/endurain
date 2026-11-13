"""78: updated_at and tombstones for incremental sync

Adds ``updated_at`` to every record ``GET /sync`` reports (activities, the health records, health targets, gear and
gear components), with an index on ``(user_id, updated_at, id)`` for the keyset walk. An existing row is stamped
with the migration's time, and an activity with its ``created_at``, so a first sync reports every record either way.

Adds the tombstone tables the owning modules write in the transaction of a delete: ``activity_deletions``,
``health_record_deletions`` (with the health record's sync type), ``gear_deletions`` and
``gear_component_deletions``, each indexed on ``(user_id, deleted_at, id)``.

Revision ID: b78d2f6a9c41
Revises: a77c4e8f1b26
Create Date: 2026-11-11 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b78d2f6a9c41"
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


def upgrade() -> None:
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


def downgrade() -> None:
    """Drop the tombstone tables and the stamps."""
    for table, index, _ in reversed(_TOMBSTONES):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
    for table, index in reversed(_SYNCED):
        op.drop_index(index, table_name=table)
        op.drop_column(table, "updated_at")
