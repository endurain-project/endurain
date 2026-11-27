"""Add the retained activity files table and the activity's reference to it

``activity_files`` holds one row per retained original activity file: its owner, SHA-256, storage key, extension,
size and state (``pending`` while the blob is written, ``attached`` once an activity references it, ``deleting``
while the blob is removed). A user has one live row per SHA-256. ``activities.file_id`` references the row an
activity was imported from; it is NULL for every activity that exists before this revision, whose files a later data
migration adopts, and stays NULL for a multisport leg.

The downgrade drops the column and the table; the blobs stay in storage.

Revision ID: 7d4a9c1e6b52
Revises: 5b8e2d4f6a13
Create Date: 2026-11-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d4a9c1e6b52"
down_revision: str | None = "5b8e2d4f6a13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``activity_files`` and add ``activities.file_id``."""
    op.create_table(
        "activity_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            comment="User ID that owns the retained file",
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False, comment="Hex SHA-256 of the file's bytes"),
        sa.Column(
            "storage_key",
            sa.String(length=255),
            nullable=False,
            comment="Key of the file's blob in the activity-files storage area",
        ),
        sa.Column(
            "extension",
            sa.String(length=8),
            nullable=False,
            comment="File extension with its dot (.gpx, .fit or .tcx)",
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, comment="Size of the file in bytes"),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            comment=(
                "pending (blob being written), attached (an activity references it) or deleting (blob being removed)"
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the row was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the row last changed state or was taken again by an upload",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint("state IN ('pending', 'attached', 'deleting')", name="ck_activity_files_state"),
    )
    op.create_index("ix_activity_files_user_id", "activity_files", ["user_id"])
    op.create_index(
        "uq_activity_files_user_sha256_live",
        "activity_files",
        ["user_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("state <> 'deleting'"),
    )
    op.create_index(
        "ix_activity_files_state_updated_at",
        "activity_files",
        ["state", "updated_at"],
        postgresql_where=sa.text("state <> 'attached'"),
    )
    op.add_column(
        "activities",
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("activity_files.id"),
            nullable=True,
            comment=(
                "Retained source file the activity was imported from; NULL for a leg or an activity with no file row"
            ),
        ),
    )
    op.create_index("ix_activities_file_id", "activities", ["file_id"])


def downgrade() -> None:
    """Drop ``activities.file_id`` and ``activity_files``."""
    op.drop_index("ix_activities_file_id", table_name="activities")
    op.drop_column("activities", "file_id")
    op.drop_table("activity_files")
