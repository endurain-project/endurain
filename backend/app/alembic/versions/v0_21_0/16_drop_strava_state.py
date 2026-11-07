"""16: drop the stored Strava OAuth state

The one-time state that ties a Strava OAuth callback to its user now lives in the platform's
shared state with a short lifetime, so the column and whatever a link in progress left in it
are no longer used.

Revision ID: b4f1c8e2a7d9
Revises: a8d3e5c1f7b2
Create Date: 2026-11-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4f1c8e2a7d9"
down_revision: str | None = "a8d3e5c1f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the stored OAuth state."""
    op.drop_column("users_integrations", "strava_state")


def downgrade() -> None:
    """Restore the empty OAuth state column."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "strava_state",
            sa.String(length=45),
            nullable=True,
            comment="Strava temporary state for link process",
        ),
    )
