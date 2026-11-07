"""24: index the columns the auth purges filter on

The scheduled purges of password-reset tokens, sign-up tokens and sessions delete by expiry (and, for
sessions, by last activity) one bounded batch at a time. Without an index each batch scans the whole
table, so the columns they filter on are indexed.

Revision ID: 8c4e2a6f0d93
Revises: 3b7d9e1f5a20
Create Date: 2026-10-29 00:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "8c4e2a6f0d93"
down_revision: str | None = "3b7d9e1f5a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("password_reset_tokens", "expires_at"),
    ("sign_up_tokens", "expires_at"),
    ("users_sessions", "expires_at"),
    ("users_sessions", "last_activity_at"),
)


def upgrade() -> None:
    """Create the purge indexes."""
    for table, column in _INDEXES:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)


def downgrade() -> None:
    """Drop the purge indexes."""
    for table, column in reversed(_INDEXES):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
