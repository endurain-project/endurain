"""11: add processing_jobs durable job queue table

Revision ID: a1f2b3c4d5e6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1f2b3c4d5e6"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Job identifier (UUIDv4)"),
        sa.Column(
            "event_id",
            sa.String(length=36),
            nullable=False,
            comment="Originating envelope event_id (correlation + dedup with subscriber_id)",
        ),
        sa.Column(
            "event_type", sa.String(length=100), nullable=False, comment="Domain-event channel, e.g. activity.created"
        ),
        sa.Column(
            "subscriber_id",
            sa.String(length=200),
            nullable=False,
            comment="Durable subscriber this job runs, e.g. activity_thumbnail.generate",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="Where the originating event came from, e.g. api:store_activity",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Domain payload the subscriber consumes",
        ),
        sa.Column(
            "job_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Correlation context (request_id, user_id, activity_id)",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
            comment="pending | claimed | completed | dead_letter",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Processing attempts so far; incremented when claimed",
        ),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, comment="Attempt ceiling before the job is dead-lettered"
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Earliest instant the job may be claimed (backoff gate)",
        ),
        sa.Column(
            "locked_by", sa.String(length=100), nullable=True, comment="Worker holding the current lease, when claimed"
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True, comment="When the current lease was taken"),
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the current lease expires (drives reaping)",
        ),
        sa.Column("last_error", sa.Text(), nullable=True, comment="Most recent failure reason (truncated for storage)"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the job was enqueued",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the job last changed state",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the job reached a terminal state (completed/dead_letter)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "subscriber_id", name="uq_processing_jobs_event_subscriber"),
    )
    op.create_index("idx_processing_jobs_claim", "processing_jobs", ["status", "available_at"])
    op.create_index("idx_processing_jobs_lease", "processing_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("idx_processing_jobs_lease", table_name="processing_jobs")
    op.drop_index("idx_processing_jobs_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
