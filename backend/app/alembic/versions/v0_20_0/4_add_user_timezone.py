"""4: add users.timezone

Revision ID: d1f4a6b8c093
Revises: 95e5558ce7a2
Create Date: 2026-07-26 00:00:00.000000

Adds the athlete's own IANA timezone, used as the fallback when an imported
activity carries no timezone of its own — no GPS track to resolve one from and
no UTC offset reported by the file (indoor rides, treadmill runs, pool swims).

Those activities previously inherited the *server's* ``TZ`` setting, so a US
athlete on a European-hosted instance had their treadmill runs stamped with a
European timezone. That value is not cosmetic: it drives both the displayed
start time and — since the summary buckets are computed in the activity's own
timezone — which day, week, month and year the activity is counted in.

Resolution order after this migration, most specific first:

1. the file's own signal (GPS point, or a FIT ``time_offset``);
2. ``users.timezone`` (this column);
3. ``settings.TZ``.

Nullable with **no backfill**. Existing activities keep whatever timezone they
were already stamped with — re-stamping them would silently move past activities
between summary buckets — and the new fallback applies to imports from here on.
``NULL`` means "not set", which the resolution chain treats as "fall back to the
server timezone", i.e. exactly the behaviour before this column existed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f4a6b8c093"
down_revision: str | None = "95e5558ce7a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=250),
            nullable=True,
            comment=("User IANA timezone, used as the fallback for activities with no GPS track"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
