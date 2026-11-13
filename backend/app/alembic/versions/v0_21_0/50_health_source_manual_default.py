"""50: every health record has a source, ``manual`` by default

Weight, steps, sleep and water stored ``NULL`` for a record a person entered, while poop and fasting stored
``manual``. The six ``source`` columns are now ``NOT NULL`` with the server default ``manual``. A ``NULL`` becomes
``manual``, except a sleep record that carries a Garmin Connect sleep id, which is ``garmin``.

Revision ID: e5b7a3d9c142
Revises: a4d8f1c6b273
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b7a3d9c142"
down_revision: str | None = "a4d8f1c6b273"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("health_weight", "health_steps", "health_sleep", "health_water", "health_poop", "health_fasting")


def _length(table: str) -> int:
    """Return the length of the table's ``source`` column."""
    return 20 if table == "health_fasting" else 250


def upgrade() -> None:
    """Give a source to every record without one, then require it."""
    op.execute("UPDATE health_sleep SET source = 'garmin' WHERE source IS NULL AND garminconnect_sleep_id IS NOT NULL")
    for table in _TABLES:
        record = sa.table(table, sa.column("source", sa.String))
        op.execute(sa.update(record).where(record.c.source.is_(None)).values(source="manual"))
        op.alter_column(
            table,
            "source",
            existing_type=sa.String(length=_length(table)),
            nullable=False,
            server_default="manual",
        )


def downgrade() -> None:
    """Allow a missing source again; the values stay as they are."""
    for table in _TABLES:
        op.alter_column(
            table,
            "source",
            existing_type=sa.String(length=_length(table)),
            nullable=True,
            server_default=None,
        )
