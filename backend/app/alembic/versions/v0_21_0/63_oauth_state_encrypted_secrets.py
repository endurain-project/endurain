"""63: store the OAuth state's nonce and PKCE verifier encrypted

The OIDC nonce and the PKCE verifier of an identity-provider sign-in sat in ``oauth_states`` in plain text, so a copy of
the table was enough to forge the ID token or the code exchange of a sign-in in flight. Both are now stored Fernet
encrypted, which no longer fits their column lengths, so the columns become ``Text``. The existing rows hold plain text
and are deleted: a state lives ten minutes at most, so the sign-ins in flight are started again, a session waiting for
its mobile token exchange loses its state (the foreign key sets the reference to null) and answers not found, and the
user signs in again.

The downgrade deletes the rows, which hold ciphertext the old code cannot use, and narrows the columns.

Revision ID: c63e1a2b3d4f
Revises: b62d4f8a1c75
Create Date: 2026-11-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c63e1a2b3d4f"
down_revision: str | None = "b62d4f8a1c75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "oauth_states"


def upgrade() -> None:
    """Delete the plain-text states, then widen the nonce and verifier columns to hold Fernet tokens."""
    op.execute("DELETE FROM oauth_states")
    op.alter_column(
        _TABLE,
        "nonce",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=False,
        existing_comment="OIDC nonce for ID token validation",
        comment="Fernet-encrypted OIDC nonce for ID token validation",
    )
    op.alter_column(
        _TABLE,
        "idp_code_verifier",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=True,
        existing_comment="PKCE verifier sent to the identity provider at the token exchange",
        comment="Fernet-encrypted PKCE verifier sent to the identity provider at the token exchange",
    )


def downgrade() -> None:
    """Delete the encrypted states, then narrow the nonce and verifier columns back."""
    op.execute("DELETE FROM oauth_states")
    op.alter_column(
        _TABLE,
        "idp_code_verifier",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=True,
        existing_comment="Fernet-encrypted PKCE verifier sent to the identity provider at the token exchange",
        comment="PKCE verifier sent to the identity provider at the token exchange",
    )
    op.alter_column(
        _TABLE,
        "nonce",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_comment="Fernet-encrypted OIDC nonce for ID token validation",
        comment="OIDC nonce for ID token validation",
    )
