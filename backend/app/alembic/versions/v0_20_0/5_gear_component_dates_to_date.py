"""5: gear_components purchase/retired dates become DATE

Revision ID: b7c2e9d4a815
Revises: d1f4a6b8c093
Create Date: 2026-07-26 00:00:00.000000

``gear_components.purchase_date`` and ``retired_date`` were declared
``TIMESTAMPTZ`` but only ever carry a calendar date: the UI is a date picker and
the API receives ``YYYY-MM-DD``, which lands at **UTC midnight**.

That mattered because the per-component mileage query compares those columns
against ``activities.start_time``, a real instant. The window boundary was
therefore UTC midnight rather than the athlete's own midnight:

* at UTC-8, a ride at 17:00 local the day *before* a purchase is 01:00 UTC on
  the purchase day, so it was counted against a component that did not exist
  yet;
* at UTC+13, a ride at 09:00 local *on* the purchase day is 20:00 UTC the day
  before, so it was not counted at all.

Storing the true type removes the ambiguity, and the query is changed in the
same commit to compare against each activity's *local* date.

The conversion is lossless: every existing value is at UTC midnight, so
``AT TIME ZONE 'UTC'`` recovers exactly the calendar day the user picked. The
downgrade re-inflates each date to midnight UTC, which is byte-for-byte what
was stored before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c2e9d4a815"
down_revision: str | None = "d1f4a6b8c093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("purchase_date", False, "Gear component purchase date (Date)"),
    ("retired_date", True, "Gear component retired date (Date)"),
)


def upgrade() -> None:
    for name, nullable, comment in _COLUMNS:
        op.alter_column(
            "gear_components",
            name,
            type_=sa.Date(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            # Values were written at UTC midnight; strip the zone before casting
            # so the stored calendar day survives verbatim.
            postgresql_using=f"{name} AT TIME ZONE 'UTC'",
            comment=comment,
        )


def downgrade() -> None:
    for name, nullable, _comment in _COLUMNS:
        op.alter_column(
            "gear_components",
            name,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.Date(),
            existing_nullable=nullable,
            postgresql_using=f"{name}::timestamp AT TIME ZONE 'UTC'",
            comment=f"Gear component {name.split('_')[0]} date (DateTime)",
        )
