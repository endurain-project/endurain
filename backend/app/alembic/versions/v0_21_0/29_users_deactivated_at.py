"""29: record when an account was deactivated

An inactive account was either deactivated (by an administrator or a deletion request) or a sign-up not yet
verified or approved, and the row did not say which, so an email verification link could reactivate an
account an administrator had deactivated. ``deactivated_at`` marks a deactivation; a sign-up has none.

Existing rows are backfilled where the state proves a deactivation: an inactive account whose email is
verified and that is not awaiting approval. A sign-up (``_stage_signup_user``) is inactive only while its
email is unverified (``stage_email_verification`` verifies and activates it) or while it awaits approval
(``approve_user`` clears the flag and activates it), so such a row can only have been deactivated. The one
exception is an account created by a first identity-provider sign-in with the provider-verified email while
the server requires email verification: it starts inactive, verified and not awaiting approval, and is
marked deactivated too, so a verification link no longer activates it. Every other row stays null.

Revision ID: 8c4e1b7d3a96
Revises: 5a8d2c6f1b73
Create Date: 2026-10-30 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c4e1b7d3a96"
down_revision: str | None = "5a8d2c6f1b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the deactivation time and backfill the accounts that are provably deactivated."""
    op.add_column(
        "users",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "When the account was deactivated by an administrator or a deletion request; "
                "null for an active account and for a sign-up not yet verified or approved"
            ),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET deactivated_at = now() "
            "WHERE active = false AND pending_admin_approval = false AND email_verified = true"
        )
    )


def downgrade() -> None:
    """Drop the deactivation time."""
    op.drop_column("users", "deactivated_at")
