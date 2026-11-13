"""69: record the account security generation an email-change token was issued under

A pending email change is a proof: a security change after the request, such as a password reset, ends it. The column
holds the generation of the account when the change was requested, and the confirmation is refused when it no longer
matches. There is no backfill: a change that is pending at the upgrade keeps null and is refused when confirmed,
which only ends changes that were requested in the last 24 hours. Sign-up tokens keep null and are never checked.

Revision ID: f69b5d8e0c24
Revises: e68a4c7d9b13
Create Date: 2026-11-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f69b5d8e0c24"
down_revision: str | None = "e68a4c7d9b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable generation column."""
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "security_generation",
            sa.Integer(),
            nullable=True,
            comment="Account security generation an email-change token was issued under (email-change tokens only)",
        ),
    )


def downgrade() -> None:
    """Drop the generation column."""
    op.drop_column("sign_up_tokens", "security_generation")
