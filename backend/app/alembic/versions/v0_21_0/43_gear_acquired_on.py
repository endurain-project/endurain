"""43: store the day a gear was acquired as a date

``gear.created_at`` was never a server timestamp: the gear form asks the user for the date they acquired the
gear and stores what they pick. The column is renamed ``acquired_on`` and becomes a ``DATE``; each row keeps
the UTC calendar day of its stored value. A gear created without a date gets the current date.

The downgrade turns each date back into a timestamp at midnight UTC.

Revision ID: a3e7c1b5d928
Revises: f2c6a9d4b871
Create Date: 2026-11-04 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3e7c1b5d928"
down_revision: str | None = "f2c6a9d4b871"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename the column, convert it to its UTC calendar day and default new rows to today."""
    op.execute("ALTER TABLE gear RENAME COLUMN created_at TO acquired_on")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on DROP DEFAULT")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on TYPE date USING (acquired_on AT TIME ZONE 'UTC')::date")
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on SET DEFAULT CURRENT_DATE")
    op.execute("COMMENT ON COLUMN gear.acquired_on IS 'Date the user acquired the gear (today when not given)'")


def downgrade() -> None:
    """Rename the column back and turn each date into midnight UTC."""
    op.execute("ALTER TABLE gear ALTER COLUMN acquired_on DROP DEFAULT")
    op.execute(
        "ALTER TABLE gear ALTER COLUMN acquired_on TYPE timestamptz USING acquired_on::timestamp AT TIME ZONE 'UTC'"
    )
    op.execute("ALTER TABLE gear RENAME COLUMN acquired_on TO created_at")
    op.execute("COMMENT ON COLUMN gear.created_at IS 'Gear creation date (DateTime)'")
