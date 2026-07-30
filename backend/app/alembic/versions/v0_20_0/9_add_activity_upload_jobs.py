"""9: add activity_upload_jobs

Revision ID: c4f7a1e93b52
Revises: a83e6b2f47d1
Create Date: 2026-07-28 00:00:00.000000

Backs the user-facing half of an activity upload. The upload route now answers
``202`` as soon as the bytes are staged and hands the parse to a background
worker, so the client needs something to poll: this table is that handle.

It is deliberately separate from ``processing_jobs``. That table is the generic
execution substrate — leases, attempt counts, and a ``last_error`` holding raw
exception text — and is admin-only for good reason. This one is scoped to a
user, carries only a closed set of sanitized error codes, and stays identical
whether the work ran on the durable worker or on the in-process fallback pool,
so the client contract does not depend on ``JOBS_ENABLED``.

``staged_key`` holds the storage key of the uploaded blob between the request
and the worker and is cleared once consumed, which is also what makes a retry
after a successful import a no-op instead of a double import. The blob itself
goes through the platform ``StorageProvider``, so the worker that parses it does
not have to be on the node that received it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f7a1e93b52"
down_revision: str | None = "a83e6b2f47d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_upload_jobs",
        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
            comment="Upload job identifier (UUIDv4 string)",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="User that owns the upload",
        ),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
            comment="Original client filename, for display only",
        ),
        sa.Column(
            "staged_key",
            sa.String(length=500),
            nullable=True,
            comment="Storage key of the staged upload; cleared once consumed",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
            comment="pending | processing | completed | failed",
        ),
        sa.Column(
            "error_code",
            sa.String(length=50),
            nullable=True,
            comment="Sanitized failure reason when status is failed",
        ),
        sa.Column(
            "activity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Ids of the activities the import created",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the upload was accepted",
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
            comment="When the job reached a terminal state (completed/failed)",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_upload_jobs_user_id"),
        "activity_upload_jobs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "idx_activity_upload_jobs_user_created",
        "activity_upload_jobs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_activity_upload_jobs_user_created", table_name="activity_upload_jobs")
    op.drop_index(op.f("ix_activity_upload_jobs_user_id"), table_name="activity_upload_jobs")
    op.drop_table("activity_upload_jobs")
