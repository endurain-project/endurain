"""16: record bulk_import as an ingestion job kind

Revision ID: 7ac9b04e1d38
Revises: 6efe1eb558f2
Create Date: 2026-08-21 00:00:00.000000

Bulk import now returns one job handle per dropped file instead of a message,
so ``kind`` gains a third value. Only the column comment changes: ``kind`` is a
plain ``String(20)`` rather than a database enum precisely so a new ingestion
kind does not need a type migration, and the comment is the documentation the
column carries.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ac9b04e1d38"
down_revision: str | None = "6efe1eb558f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "activity_ingestion_jobs",
        "kind",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="upload",
        comment="upload | refresh | bulk_import",
        existing_comment="upload | refresh",
    )


def downgrade() -> None:
    # A bulk-import job cannot be represented by the older comment's vocabulary,
    # and its rows are pure history — drop them rather than leave the column
    # documenting a value it still holds.
    op.execute("DELETE FROM activity_ingestion_jobs WHERE kind = 'bulk_import'")
    op.alter_column(
        "activity_ingestion_jobs",
        "kind",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="upload",
        comment="upload | refresh",
        existing_comment="upload | refresh | bulk_import",
    )
