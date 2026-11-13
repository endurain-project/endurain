"""75: record the native app an SSO session was handed to

A native app signs in through SSO with a redirect address that must be on the allowed list, and the session it
receives was not tied to that address. The session now records it, so the user and an administrator can tell the
sessions held by different apps apart. It is null for web sessions, for sessions that existed before this revision
and for sign-ins that carry no redirect.

Revision ID: e75c9a3d7b24
Revises: d74b8f2c6a13
Create Date: 2026-11-10 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e75c9a3d7b24"
down_revision: str | None = "d74b8f2c6a13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable app redirect address to the sessions."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "app_redirect_uri",
            sa.String(length=500),
            nullable=True,
            comment="Native-app redirect address an SSO sign-in handed the session to",
        ),
    )


def downgrade() -> None:
    """Drop the app redirect address."""
    op.drop_column("users_sessions", "app_redirect_uri")
