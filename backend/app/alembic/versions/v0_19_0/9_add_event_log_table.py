"""9: add event_log observability table

Revision ID: e7f8a9b0c1d2
Revises: a4dd90d4f76e
Create Date: 2026-07-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "a4dd90d4f76e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_log",
        sa.Column(
            "id", sa.String(length=36), nullable=False, comment="Envelope event_id (UUIDv4); stable across retries"
        ),
        sa.Column(
            "event_type", sa.String(length=100), nullable=False, comment="Domain-event channel, e.g. activity.created"
        ),
        sa.Column(
            "event_source",
            sa.String(length=50),
            nullable=False,
            comment="Where the event originated, e.g. api:store_activity",
        ),
        sa.Column(
            "event_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Domain payload, passed through untouched",
        ),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Correlation context (request_id, user_id, activity_id)",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="published",
            nullable=False,
            comment="published | processing | completed | failed | dead_letter",
        ),
        sa.Column(
            "handler_name", sa.String(length=100), nullable=True, comment="Subscriber(s) that processed the event"
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=True, comment="Process/consumer that handled the event"),
        sa.Column(
            "error_message", sa.Text(), nullable=True, comment="Failure reason when status is failed/dead_letter"
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Processing attempts so far; 0 on first publish",
        ),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True, comment="Handler execution time in milliseconds"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the event was published",
        ),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=True, comment="When a consumer picked the event up"
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When processing finished (success or failure)",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_event_log_type_status", "event_log", ["event_type", "status"])
    op.create_index("idx_event_log_created", "event_log", ["created_at"])
    # Postgres GIN index for @> correlation queries on event_metadata.
    op.create_index(
        "idx_event_log_metadata",
        "event_log",
        ["event_metadata"],
        postgresql_using="gin",
        postgresql_ops={"event_metadata": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_event_log_metadata", table_name="event_log")
    op.drop_index("idx_event_log_created", table_name="event_log")
    op.drop_index("idx_event_log_type_status", table_name="event_log")
    op.drop_table("event_log")
