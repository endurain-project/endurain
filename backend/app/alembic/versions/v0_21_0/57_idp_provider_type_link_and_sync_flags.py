"""57: settle the identity-provider type and add the link-by-email and email-sync switches

``provider_type`` is ``oidc`` or ``oauth2``. There is no SAML code, so a ``saml`` row has always behaved exactly
like an ``oauth2`` one; it becomes ``oauth2``, which changes nothing at runtime.

``link_by_email`` says whether a sign-in with no link joins the local account with the same verified email, and
``sync_email`` whether the verified email is copied onto the account at sign-in. New providers start with both
off. Existing providers keep what they did before: they all linked by email, and they synced the email exactly
when they synced the other fields (``sync_user_info``).

Revision ID: c8e2a5f19b36
Revises: d4b8f2a61c93
Create Date: 2026-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e2a5f19b36"
down_revision: str | None = "d4b8f2a61c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Turn ``saml`` rows into ``oauth2`` and add the two switches, keeping what existing providers did."""
    op.alter_column(
        "identity_providers",
        "provider_type",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        comment="Type: oidc, oauth2",
        existing_comment="Type: oidc, oauth2, saml",
    )
    op.alter_column(
        "identity_providers",
        "sync_user_info",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment="Sync the mapped profile fields, except the email, on each login",
        existing_comment="Sync user info on each login",
    )
    op.add_column(
        "identity_providers",
        sa.Column(
            "link_by_email",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Link a sign-in with no link to the local account that has the same verified email",
        ),
    )
    op.add_column(
        "identity_providers",
        sa.Column(
            "sync_email",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Sync the verified email on each login",
        ),
    )
    op.execute("UPDATE identity_providers SET provider_type = 'oauth2' WHERE provider_type = 'saml'")
    op.execute("UPDATE identity_providers SET link_by_email = true, sync_email = sync_user_info")


def downgrade() -> None:
    """Drop the two switches. A ``saml`` row that became ``oauth2`` stays ``oauth2``: the two behave alike."""
    op.drop_column("identity_providers", "sync_email")
    op.drop_column("identity_providers", "link_by_email")
    op.alter_column(
        "identity_providers",
        "sync_user_info",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment="Sync user info on each login",
        existing_comment="Sync the mapped profile fields, except the email, on each login",
    )
    op.alter_column(
        "identity_providers",
        "provider_type",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        comment="Type: oidc, oauth2, saml",
        existing_comment="Type: oidc, oauth2",
    )
