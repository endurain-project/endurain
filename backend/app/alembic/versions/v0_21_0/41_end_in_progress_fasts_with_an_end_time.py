"""41: mark in-progress fasting sessions that have an end time as completed

A fasting session could be saved as in progress with an end time. Such a session counted as the running
fast, was given a duration and blocked starting a new one. The server now refuses the combination; this
turns the ones already stored into completed sessions, keeping their end time and duration. A duration
that was never stored is derived from the session's times, as migration 40 does, unless the end is
before the start.

Revision ID: d4b8e1a6c735
Revises: c9a3f7b15e42
Create Date: 2026-11-03 00:00:03.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b8e1a6c735"
down_revision: str | None = "c9a3f7b15e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_health_fasting = sa.table(
    "health_fasting",
    sa.column("id", sa.Integer),
    sa.column("status", sa.String),
    sa.column("fast_start_time", sa.DateTime(timezone=True)),
    sa.column("fast_end_time", sa.DateTime(timezone=True)),
    sa.column("actual_duration_seconds", sa.Integer),
    sa.column("version", sa.Integer),
)


def _utc(moment: datetime) -> datetime:
    """Return a stored time as UTC; a database that keeps no offset holds UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def upgrade() -> None:
    """Complete each in-progress session that has an end time, filling a missing duration and bumping the version."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            _health_fasting.c.id,
            _health_fasting.c.fast_start_time,
            _health_fasting.c.fast_end_time,
            _health_fasting.c.actual_duration_seconds,
        ).where(_health_fasting.c.status == "in_progress", _health_fasting.c.fast_end_time.is_not(None))
    ).all()
    for fast_id, start, end, stored in rows:
        values: dict[str, object] = {"status": "completed", "version": _health_fasting.c.version + 1}
        if stored is None:
            duration = int((_utc(end) - _utc(start)).total_seconds())
            if duration >= 0:
                values["actual_duration_seconds"] = duration
        connection.execute(sa.update(_health_fasting).where(_health_fasting.c.id == fast_id).values(**values))


def downgrade() -> None:
    """Keep the sessions completed: which ones were in progress is not recorded."""
