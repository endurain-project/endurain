"""17: add notification source event idempotency key

Revision ID: d8f4a2c6e901
Revises: 7ac9b04e1d38
Create Date: 2026-08-25 00:00:00.000000

Durable event delivery is at least once. A stable event ID lets notification
handlers identify retries, while the unique constraint closes the race between
workers that receive the same event concurrently. Existing notifications stay
unconstrained because their source event ID is NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f4a2c6e901"
down_revision: str | None = "7ac9b04e1d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "source_event_id",
            sa.String(length=36),
            nullable=True,
            comment="Durable event ID used to make event-driven creation idempotent",
        ),
    )
    op.create_unique_constraint(
        "uq_notifications_source_event_user_type",
        "notifications",
        ["source_event_id", "user_id", "type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_notifications_source_event_user_type",
        "notifications",
        type_="unique",
    )
    op.drop_column("notifications", "source_event_id")
