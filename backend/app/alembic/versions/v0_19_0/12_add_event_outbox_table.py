"""12: add event_outbox transactional-outbox table

Revision ID: c7d8e9f0a1b2
Revises: a1f2b3c4d5e6
Create Date: 2026-07-14 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "a1f2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Outbox row identifier (UUIDv4)"),
        sa.Column(
            "event_id",
            sa.String(length=36),
            nullable=False,
            comment="Envelope event_id carried onto the fanned-out jobs",
        ),
        sa.Column(
            "event_type", sa.String(length=100), nullable=False, comment="Domain-event channel, e.g. activity.created"
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="Where the event originated, e.g. api:store_activity",
        ),
        sa.Column("timestamp", sa.String(length=40), nullable=False, comment="Envelope ISO-8601 publish timestamp"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="Domain payload"),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Correlation context (request_id, user_id, activity_id)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the event was written to the outbox",
        ),
        sa.Column(
            "relayed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the relay fanned the event out; NULL while pending",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_event_outbox_relayed", "event_outbox", ["relayed_at", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_event_outbox_relayed", table_name="event_outbox")
    op.drop_table("event_outbox")
