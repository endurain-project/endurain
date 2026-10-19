"""7: add schema_version to event_outbox and processing_jobs

Revision ID: f1d94c62ab08
Revises: e4a1b8c73f26
Create Date: 2026-07-28 00:00:00.000000

An event is written by one process and read by another at a later, unbounded
time: it waits in the outbox for the relay's next pass, retries with exponential
backoff, and can sit dead-lettered indefinitely — and during a rolling deploy old
and new replicas publish and consume simultaneously. So the build that wrote a
payload is frequently not the build that reads it.

Without a version marker that skew is silent rather than loud. Every payload
model sets ``extra="ignore"``, so a consumer on a different build drops keys it
does not recognise and falls back to the default for ones it expects but cannot
find — a renamed or repurposed field is therefore read as its default and acted
on, with no error raised anywhere. Recording the version lets the consumer either
upgrade the payload through a registered migration or refuse it (raising, so the
existing retry/dead-letter machinery handles it).

Both columns backfill to 1 via the server default: every existing row was written
before the field existed and therefore carries the initial payload shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1d94c62ab08"
down_revision: str | None = "e4a1b8c73f26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event_outbox",
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment=("Version of the payload shape, so a consumer on a different build can upgrade or refuse it"),
        ),
    )
    op.add_column(
        "processing_jobs",
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Version of the payload shape, carried from the originating envelope",
        ),
    )


def downgrade() -> None:
    op.drop_column("processing_jobs", "schema_version")
    op.drop_column("event_outbox", "schema_version")
