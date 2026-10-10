"""8: widen event_log.handler_name

Revision ID: a83e6b2f47d1
Revises: f1d94c62ab08
Create Date: 2026-07-28 00:00:00.000000

``handler_name`` stores the comma-joined list of every subscriber that ran for an
event, so its length grows with the subscriber count. At ``varchar(100)`` the
list outgrew the column: ``activity.created`` (four subscribers) needs 125
characters and ``activity.deleted`` needs 101 — one over — as soon as the media
cleanup subscriber was added.

PostgreSQL rejects the whole UPDATE with ``StringDataRightTruncation``, and
because event-log writes are deliberately best-effort (the recorder swallows
storage errors so observability can never break event processing) the failure was
silent. The handlers had already run inside ``track()``, so the real work
completed while the row stayed at ``published`` forever — thumbnails generated,
files moved and deleted, but every ``activity.*`` event apparently unfinished.

Widening buys headroom; the clamp added alongside this in
``jasil/event_log/crud.py`` is what makes the write unable to fail again as more
subscribers are registered.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a83e6b2f47d1"
down_revision: str | None = "f1d94c62ab08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "event_log",
        "handler_name",
        existing_type=sa.String(length=100),
        type_=sa.String(length=500),
        existing_nullable=True,
        comment="Subscriber(s) that processed the event, comma-separated",
        existing_comment="Subscriber(s) that processed the event",
    )


def downgrade() -> None:
    # Values longer than the old width would be rejected on the way back down,
    # so trim them first rather than failing the downgrade.
    op.execute("UPDATE event_log SET handler_name = LEFT(handler_name, 100) WHERE LENGTH(handler_name) > 100")
    op.alter_column(
        "event_log",
        "handler_name",
        existing_type=sa.String(length=500),
        type_=sa.String(length=100),
        existing_nullable=True,
        comment="Subscriber(s) that processed the event",
        existing_comment="Subscriber(s) that processed the event, comma-separated",
    )
