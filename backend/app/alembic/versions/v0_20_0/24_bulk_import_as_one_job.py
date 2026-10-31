"""24: a bulk import is one job over one archive

Revision ID: 8a2f6c1d9e43
Revises: 3d7b5e9a2c64
Create Date: 2026-10-15 00:00:00.000000

A bulk import used to create one job per file. It is now one job over one staged
archive that is worked through in batches, so the job carries the format it reads,
file counters and a resume cursor, and the database allows one running import per
user.

Per-file bulk-import jobs that never finished belong to a handler that no longer
exists, so they are closed as failed first; otherwise a user with two of them
would block the unique index.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a2f6c1d9e43"
down_revision: str | None = "3d7b5e9a2c64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_activity_ingestion_jobs_user_active_bulk_import"
_ACTIVE = "kind = 'bulk_import' AND completed_at IS NULL"


def upgrade() -> None:
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "import_source",
            sa.String(length=50),
            nullable=True,
            comment="Archive format a bulk import reads (generic or a provider export)",
        ),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column("files_total", sa.Integer(), nullable=True, comment="Importable files in a bulk import's archive"),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column("files_done", sa.Integer(), nullable=True, comment="Files a bulk import has imported so far"),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column("files_failed", sa.Integer(), nullable=True, comment="Files a bulk import could not import"),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "cursor",
            sa.String(length=500),
            nullable=True,
            comment="Last archive member a bulk import handled; the next batch resumes after it",
        ),
    )
    op.execute(
        """
        UPDATE activity_ingestion_jobs
        SET status = 'failed',
            error_code = 'processing_failed',
            staged_key = NULL,
            completed_at = COALESCE(completed_at, now()),
            updated_at = now()
        WHERE kind = 'bulk_import' AND completed_at IS NULL
        """
    )
    op.create_index(
        _INDEX,
        "activity_ingestion_jobs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="activity_ingestion_jobs")
    op.drop_column("activity_ingestion_jobs", "cursor")
    op.drop_column("activity_ingestion_jobs", "files_failed")
    op.drop_column("activity_ingestion_jobs", "files_done")
    op.drop_column("activity_ingestion_jobs", "files_total")
    op.drop_column("activity_ingestion_jobs", "import_source")
