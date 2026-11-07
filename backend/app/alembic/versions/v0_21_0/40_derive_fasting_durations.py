"""40: derive the stored duration of every ended fasting session

The duration of a fasting session was written by the client and not recalculated when its times were
edited, so it drifted from the start and end times the statistics are meant to reflect. The server now
derives it; this recomputes the ones already stored for sessions that have an end time.

A session whose end is before its start has no valid duration and is left as it is.

Revision ID: c9a3f7b15e42
Revises: b6e2d4a8c031
Create Date: 2026-11-03 00:00:02.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a3f7b15e42"
down_revision: str | None = "b6e2d4a8c031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_health_fasting = sa.table(
    "health_fasting",
    sa.column("id", sa.Integer),
    sa.column("fast_start_time", sa.DateTime(timezone=True)),
    sa.column("fast_end_time", sa.DateTime(timezone=True)),
    sa.column("actual_duration_seconds", sa.Integer),
    sa.column("version", sa.Integer),
)


def _utc(moment: datetime) -> datetime:
    """Return a stored time as UTC; a database that keeps no offset holds UTC."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def upgrade() -> None:
    """Set the duration of each ended session to the seconds between its times, bumping the version when it changes."""
    connection = op.get_bind()
    stale = []
    rows = connection.execute(
        sa.select(
            _health_fasting.c.id,
            _health_fasting.c.fast_start_time,
            _health_fasting.c.fast_end_time,
            _health_fasting.c.actual_duration_seconds,
        ).where(_health_fasting.c.fast_end_time.is_not(None))
    )
    for fast_id, start, end, stored in rows:
        duration = int((_utc(end) - _utc(start)).total_seconds())
        if duration >= 0 and duration != stored:
            stale.append({"fast_id": fast_id, "duration": duration})
    if stale:
        connection.execute(
            sa.update(_health_fasting)
            .where(_health_fasting.c.id == sa.bindparam("fast_id"))
            .values(actual_duration_seconds=sa.bindparam("duration"), version=_health_fasting.c.version + 1),
            stale,
        )


def downgrade() -> None:
    """Keep the derived durations: the values they replaced were not the sessions' real durations."""
