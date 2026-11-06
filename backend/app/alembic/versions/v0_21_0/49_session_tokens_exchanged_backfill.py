"""49: mark sessions that already hold a refresh token as exchanged

A password sign-in creates its session with the refresh token, so it needs no token exchange, yet the
session was stored with ``tokens_exchanged`` false. Session lists now hide sessions whose exchange has not
happened, so those rows are marked exchanged.

Revision ID: a4d8f1c6b273
Revises: c9f2d6a3e851
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d8f1c6b273"
down_revision: str | None = "c9f2d6a3e851"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Mark every session that holds a refresh token as exchanged."""
    op.execute(
        "UPDATE users_sessions SET tokens_exchanged = true WHERE refresh_token IS NOT NULL AND tokens_exchanged = false"
    )


def downgrade() -> None:
    """Leave the rows as they are: whether a session was once unexchanged cannot be recovered."""
