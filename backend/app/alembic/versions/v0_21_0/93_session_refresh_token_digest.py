"""93: store refresh tokens as keyed digests and end the sessions open before it

A session stored the Argon2 hash of its refresh token, and every refresh paid for a verify and a hash of 64 MiB each
while holding the session row. A refresh token is 256 bits of signed random data, so a session now stores an
HMAC-SHA256 digest of it, as rotated refresh tokens and CSRF tokens already do. A digest cannot be told from an
Argon2 hash, and the stored Argon2 hashes never match a digest, so the open sessions are deleted instead of left
unusable: every user signs in once more. Deleting a session deletes its rotated refresh tokens (foreign key with
``ON DELETE CASCADE``); the identity-provider tokens of those sessions, which have no foreign key, are revoked at the
provider by the scheduled sweep of ended sessions.

The downgrade has nothing to restore; the sessions the upgrade ended stay ended.

Revision ID: c93f5a8d1b47
Revises: 1087a5442836
Create Date: 2026-11-13 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c93f5a8d1b47"
down_revision: str | None = "1087a5442836"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """End every session, whose stored refresh-token hash would never match a digest."""
    op.execute("DELETE FROM users_sessions")


def downgrade() -> None:
    """Do nothing: the sessions the upgrade ended stay ended."""
