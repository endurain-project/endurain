"""86: align the schema with the models

``activity_sets.start_time`` becomes ``timestamptz``; the naive values are read in the session time zone (UTC, which
the application's engine pins), the way the application wrote them. Four column comments follow the model text.

Revision ID: 3e7a91d4c0b8
Revises: b41c0afdc9d9
Create Date: 2026-11-12 09:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e7a91d4c0b8"
down_revision: str | None = "b41c0afdc9d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, existing type, nullable, old comment, new comment)
_COMMENTS = (
    (
        "activity_ingestion_jobs",
        "id",
        sa.String(length=36),
        False,
        "Upload job identifier (UUIDv4 string)",
        "Ingestion job identifier (UUIDv4 string)",
    ),
    (
        "activity_ingestion_jobs",
        "user_id",
        sa.Integer(),
        False,
        "User that owns the upload",
        "User that owns the ingestion request",
    ),
    (
        "activity_ingestion_jobs",
        "created_at",
        sa.DateTime(timezone=True),
        False,
        "When the upload was accepted",
        "When the request was accepted",
    ),
    (
        "health_record_deletions",
        "record_type",
        sa.String(length=50),
        False,
        "Sync type of the record",
        "Sync type of the deleted record, e.g. health_weight",
    ),
)


def upgrade() -> None:
    """Make ``activity_sets.start_time`` timezone-aware and update the four column comments."""
    op.alter_column(
        "activity_sets",
        "start_time",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_comment="Workout set start date",
    )
    for table, column, existing_type, nullable, old_comment, new_comment in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=existing_type,
            existing_nullable=nullable,
            existing_comment=old_comment,
            comment=new_comment,
        )


def downgrade() -> None:
    """Restore the naive ``activity_sets.start_time`` and the four earlier column comments."""
    for table, column, existing_type, nullable, old_comment, new_comment in _COMMENTS:
        op.alter_column(
            table,
            column,
            existing_type=existing_type,
            existing_nullable=nullable,
            existing_comment=new_comment,
            comment=old_comment,
        )
    op.alter_column(
        "activity_sets",
        "start_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_comment="Workout set start date",
    )
