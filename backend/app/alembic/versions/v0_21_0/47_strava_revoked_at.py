"""47: record when Strava access was revoked

``users_integrations.strava_revoked_at`` marks the moment Strava refused the user's refresh token. A
recurring job deletes the user's Strava API data once the grace period after it has passed, unless the
user relinks first.

Revision ID: b4c8e1f7a362
Revises: d2b6c8e4f193
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c8e1f7a362"
down_revision: str | None = "d2b6c8e4f193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable revocation timestamp."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "strava_revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When Strava refused the refresh token; Strava data is deleted after the grace period",
        ),
    )


def downgrade() -> None:
    """Drop the revocation timestamp."""
    op.drop_column("users_integrations", "strava_revoked_at")
