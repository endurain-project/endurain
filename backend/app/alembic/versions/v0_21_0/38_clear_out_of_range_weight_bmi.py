"""38: clear stored weight BMIs outside the valid range

A BMI above 100 (for example from a height typed in the wrong unit) made every read of
the user's weight records fail validation. The calculation now leaves such a BMI empty;
this clears the ones already stored.

Revision ID: 7c3e9a1d5b24
Revises: 4f2b8c6e1a93
Create Date: 2026-11-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c3e9a1d5b24"
down_revision: str | None = "4f2b8c6e1a93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Set the BMI of every weight record outside 0 to 100 to NULL, bumping the version a client's ETag names."""
    op.execute(sa.text("UPDATE health_weight SET bmi = NULL, version = version + 1 WHERE bmi > 100 OR bmi < 0"))


def downgrade() -> None:
    """Keep the cleared values: the BMI they held was not valid and cannot be recovered."""
