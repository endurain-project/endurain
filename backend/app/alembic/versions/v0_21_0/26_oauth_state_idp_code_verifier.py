"""26: use PKCE between this server and the identity provider

An SSO login or link now sends the provider an S256 code challenge and proves it at the token exchange with
a verifier kept on the OAuth state, so an authorization code that leaks before it is used cannot be redeemed
by anyone else.

States are short-lived, so existing rows are left without a verifier and finish without PKCE.

Revision ID: 9d2b6e4a7c15
Revises: 5f1a8c3e9b27
Create Date: 2026-10-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d2b6e4a7c15"
down_revision: str | None = "5f1a8c3e9b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the provider PKCE verifier."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "idp_code_verifier",
            sa.String(length=128),
            nullable=True,
            comment="PKCE verifier sent to the identity provider at the token exchange",
        ),
    )


def downgrade() -> None:
    """Drop the provider PKCE verifier."""
    op.drop_column("oauth_states", "idp_code_verifier")
