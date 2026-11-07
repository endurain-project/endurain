"""58: record the client type of each session and end the sessions open before it

A session now records the kind of client it was created for (``web`` or ``mobile``); its tokens name it in the
``client_id`` claim and a refresh must declare it. Refresh tokens are now signed with a key of their own and carry
the refresh endpoint as their audience, so no refresh token issued before this revision verifies any more. The open
sessions are deleted instead of being given a guessed client type: every user signs in once more. Deleting a session
deletes its rotated refresh tokens (foreign key with ``ON DELETE CASCADE``); the identity-provider tokens of those
sessions, which have no foreign key, are revoked at the provider by the scheduled sweep of ended sessions.

The downgrade drops the column; the sessions ended by the upgrade do not come back.

Revision ID: a10c7e3f5d21
Revises: c8e2a5f19b36
Create Date: 2026-11-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a10c7e3f5d21"
down_revision: str | None = "c8e2a5f19b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users_sessions"
_CHECK = "ck_users_sessions_client_type"


def upgrade() -> None:
    """End every session, then add the non-null client type limited to ``web`` and ``mobile``."""
    op.execute("DELETE FROM users_sessions")
    op.add_column(
        _TABLE,
        sa.Column(
            "client_type",
            sa.String(length=10),
            nullable=False,
            comment="Client type the session was created for: web or mobile",
        ),
    )
    op.create_check_constraint(_CHECK, _TABLE, "client_type IN ('web', 'mobile')")


def downgrade() -> None:
    """Drop the client type; the sessions the upgrade ended stay ended."""
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "client_type")
