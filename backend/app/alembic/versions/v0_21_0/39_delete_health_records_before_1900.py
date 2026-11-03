"""39: delete health records dated before 1900

A record dated before 1900 (a mistyped year) cannot be a real measurement and broke the charts
that group records by day. Requests are now refused for such dates; this deletes the records
already stored.

Revision ID: b6e2d4a8c031
Revises: 7c3e9a1d5b24
Create Date: 2026-11-03 00:00:01.000000

"""

from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6e2d4a8c031"
down_revision: str | None = "7c3e9a1d5b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EARLIEST_DATE = date(1900, 1, 1)
_EARLIEST_DATETIME = datetime(1900, 1, 1, tzinfo=UTC)

# table -> (column that dates the record, the column's type, the earliest value it may hold)
_DATED = {
    "health_steps": ("date", sa.Date(), _EARLIEST_DATE),
    "health_water": ("date", sa.Date(), _EARLIEST_DATE),
    "health_weight": ("date", sa.Date(), _EARLIEST_DATE),
    "health_sleep": ("date", sa.Date(), _EARLIEST_DATE),
    "health_poop": ("date_time", sa.DateTime(timezone=True), _EARLIEST_DATETIME),
    "health_fasting": ("fast_start_time", sa.DateTime(timezone=True), _EARLIEST_DATETIME),
}


def upgrade() -> None:
    """Delete every record that is dated before 1900-01-01."""
    for table_name, (column_name, column_type, earliest) in _DATED.items():
        table = sa.table(table_name, sa.column(column_name, column_type))
        op.execute(sa.delete(table).where(table.c[column_name] < earliest))


def downgrade() -> None:
    """Keep the deleted records gone: they were invalid and cannot be restored."""
