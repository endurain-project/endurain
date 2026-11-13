"""28: record the address a sign-up token proves and the address an email change replaces

A sign-up token carried only its user, so an email-change link could not name the address it confirmed
and the new address was written to the account before it was verified. A token now records the address
it proves in ``email`` and, on an email-change token, the account's address at the time of the request in
``previous_email``, so a pending change lives on the token until it is confirmed.

Existing rows keep both columns empty: they are short-lived and were issued for the account's own address.

Revision ID: 5a8d2c6f1b73
Revises: 3e7c1a9d5b42
Create Date: 2026-10-30 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a8d2c6f1b73"
down_revision: str | None = "3e7c1a9d5b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the proven address and the replaced address."""
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "email",
            sa.String(length=250),
            nullable=True,
            comment="Email address the token proves (empty on tokens issued before the column existed)",
        ),
    )
    op.add_column(
        "sign_up_tokens",
        sa.Column(
            "previous_email",
            sa.String(length=250),
            nullable=True,
            comment="Account email address when an email change was requested (email-change tokens only)",
        ),
    )


def downgrade() -> None:
    """Drop the proven address and the replaced address."""
    op.drop_column("sign_up_tokens", "previous_email")
    op.drop_column("sign_up_tokens", "email")
