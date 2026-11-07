"""56: keep the ID token each identity-provider sign-in was issued

RP-initiated logout (OpenID Connect RP-Initiated Logout 1.0) names the session to end with the ID token the
provider issued at sign-in, so the sign-in keeps it, encrypted like the refresh token. Existing sign-ins hold none:
signing out of such a session ends only the Endurain session.

Revision ID: d4b8f2a61c93
Revises: a7e3c19d5b42
Create Date: 2026-11-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b8f2a61c93"
down_revision: str | None = "a7e3c19d5b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column, empty for every existing sign-in."""
    op.add_column(
        "idp_session_tokens",
        sa.Column("id_token", sa.Text(), nullable=True, comment="Encrypted ID token the provider issued at sign-in"),
    )


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("idp_session_tokens", "id_token")
