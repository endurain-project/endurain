"""10: generalize activity_upload_jobs into activity_ingestion_jobs

Revision ID: 5b21c7d84a9e
Revises: c4f7a1e93b52
Create Date: 2026-07-28 00:00:00.000000

Provider refresh now answers ``202`` and runs on a background worker, exactly as
uploads do, so it needs the same pollable handle. Rather than a second
near-identical table, the upload table becomes the ingestion table with a
``kind`` discriminator: an upload and a refresh differ in how the activities are
obtained, not in what the caller needs to know about progress, so one row shape
gives the client one thing to poll.

``filename`` and ``staged_key`` become upload-only, hence nullable. Existing rows
are all uploads, which is why ``kind`` defaults to ``upload`` — the backfill is
the server default.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b21c7d84a9e"
down_revision: str | None = "c4f7a1e93b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("activity_upload_jobs", "activity_ingestion_jobs")
    # rename_table leaves indexes and constraints on their old names, which would
    # leave a table full of "upload" identifiers. The auto-generated NOT NULL
    # constraint names are deliberately left alone: Postgres owns those and
    # their naming is version-specific.
    op.execute("ALTER INDEX ix_activity_upload_jobs_user_id RENAME TO ix_activity_ingestion_jobs_user_id")
    op.execute("ALTER INDEX idx_activity_upload_jobs_user_created RENAME TO idx_activity_ingestion_jobs_user_created")
    op.execute(
        "ALTER TABLE activity_ingestion_jobs "
        "RENAME CONSTRAINT activity_upload_jobs_pkey TO activity_ingestion_jobs_pkey"
    )
    op.execute(
        "ALTER TABLE activity_ingestion_jobs "
        "RENAME CONSTRAINT activity_upload_jobs_user_id_fkey TO activity_ingestion_jobs_user_id_fkey"
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "kind",
            sa.String(length=20),
            server_default="upload",
            nullable=False,
            comment="upload | refresh",
        ),
    )
    op.alter_column(
        "activity_ingestion_jobs",
        "filename",
        existing_type=sa.String(length=255),
        nullable=True,
        comment="Original client filename for an upload, for display only",
        existing_comment="Original client filename, for display only",
    )


def downgrade() -> None:
    # A refresh job has no filename, so it cannot be represented once the column
    # is NOT NULL again; drop those rows rather than invent a value for them.
    op.execute("DELETE FROM activity_ingestion_jobs WHERE kind = 'refresh'")
    op.alter_column(
        "activity_ingestion_jobs",
        "filename",
        existing_type=sa.String(length=255),
        nullable=False,
        comment="Original client filename, for display only",
        existing_comment="Original client filename for an upload, for display only",
    )
    op.drop_column("activity_ingestion_jobs", "kind")
    op.execute(
        "ALTER TABLE activity_ingestion_jobs "
        "RENAME CONSTRAINT activity_ingestion_jobs_user_id_fkey TO activity_upload_jobs_user_id_fkey"
    )
    op.execute(
        "ALTER TABLE activity_ingestion_jobs "
        "RENAME CONSTRAINT activity_ingestion_jobs_pkey TO activity_upload_jobs_pkey"
    )
    op.execute("ALTER INDEX idx_activity_ingestion_jobs_user_created RENAME TO idx_activity_upload_jobs_user_created")
    op.execute("ALTER INDEX ix_activity_ingestion_jobs_user_id RENAME TO ix_activity_upload_jobs_user_id")
    op.rename_table("activity_ingestion_jobs", "activity_upload_jobs")
