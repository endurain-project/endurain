"""18: align the legacy JASIL schema for adoption

Revision ID: e3b7a91c4d62
Revises: d8f4a2c6e901
Create Date: 2026-09-04 00:00:00.000000

Endurain created the PostgreSQL GIN index before JASIL owned its migration
history. JASIL 0.5 validates the physical schema before adopting unversioned
tables and uses ``idx_event_log_metadata_gin`` as the canonical index name.
Rename the equivalent legacy index and normalize host-specific column comments
before startup hands schema ownership to JASIL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b7a91c4d62"
down_revision: str | None = "d8f4a2c6e901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER INDEX idx_event_log_metadata RENAME TO idx_event_log_metadata_gin")
    op.alter_column(
        "event_log",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. order.created",
        existing_comment="Domain-event channel, e.g. activity.created",
    )
    op.alter_column(
        "event_log",
        "event_source",
        existing_type=sa.String(length=50),
        comment="Where the event originated, e.g. api:create_order",
        existing_comment="Where the event originated, e.g. api:store_activity",
    )
    op.alter_column(
        "event_log",
        "event_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, plus any host-defined keys)",
        existing_comment="Correlation context (request_id, user_id, activity_id)",
    )
    op.alter_column(
        "event_outbox",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. order.created",
        existing_comment="Domain-event channel, e.g. activity.created",
    )
    op.alter_column(
        "event_outbox",
        "source",
        existing_type=sa.String(length=50),
        comment="Where the event originated, e.g. api:create_order",
        existing_comment="Where the event originated, e.g. api:store_activity",
    )
    op.alter_column(
        "event_outbox",
        "event_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, plus any host-defined keys)",
        existing_comment="Correlation context (request_id, user_id, activity_id)",
    )
    op.alter_column(
        "processing_jobs",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. order.created",
        existing_comment="Domain-event channel, e.g. activity.created",
    )
    op.alter_column(
        "processing_jobs",
        "subscriber_id",
        existing_type=sa.String(length=200),
        comment="Durable subscriber this job runs, e.g. invoice.render",
        existing_comment="Durable subscriber this job runs, e.g. activity_thumbnail.generate",
    )
    op.alter_column(
        "processing_jobs",
        "job_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, plus any host-defined keys)",
        existing_comment="Correlation context (request_id, user_id, activity_id)",
    )


def downgrade() -> None:
    op.alter_column(
        "processing_jobs",
        "job_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, user_id, activity_id)",
        existing_comment="Correlation context (request_id, plus any host-defined keys)",
    )
    op.alter_column(
        "processing_jobs",
        "subscriber_id",
        existing_type=sa.String(length=200),
        comment="Durable subscriber this job runs, e.g. activity_thumbnail.generate",
        existing_comment="Durable subscriber this job runs, e.g. invoice.render",
    )
    op.alter_column(
        "processing_jobs",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. activity.created",
        existing_comment="Domain-event channel, e.g. order.created",
    )
    op.alter_column(
        "event_outbox",
        "event_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, user_id, activity_id)",
        existing_comment="Correlation context (request_id, plus any host-defined keys)",
    )
    op.alter_column(
        "event_outbox",
        "source",
        existing_type=sa.String(length=50),
        comment="Where the event originated, e.g. api:store_activity",
        existing_comment="Where the event originated, e.g. api:create_order",
    )
    op.alter_column(
        "event_outbox",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. activity.created",
        existing_comment="Domain-event channel, e.g. order.created",
    )
    op.alter_column(
        "event_log",
        "event_metadata",
        existing_type=sa.JSON(),
        comment="Correlation context (request_id, user_id, activity_id)",
        existing_comment="Correlation context (request_id, plus any host-defined keys)",
    )
    op.alter_column(
        "event_log",
        "event_source",
        existing_type=sa.String(length=50),
        comment="Where the event originated, e.g. api:store_activity",
        existing_comment="Where the event originated, e.g. api:create_order",
    )
    op.alter_column(
        "event_log",
        "event_type",
        existing_type=sa.String(length=100),
        comment="Domain-event channel, e.g. activity.created",
        existing_comment="Domain-event channel, e.g. order.created",
    )
    op.execute("ALTER INDEX idx_event_log_metadata_gin RENAME TO idx_event_log_metadata")
