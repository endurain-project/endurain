"""31: flag identity providers that have an uploaded icon

The icon column held a built-in key or a custom icon URL, and a URL on another host is blocked by the page's
Content-Security-Policy. ``icon_uploaded`` marks a provider whose icon is stored in Endurain and served from it;
it is set only by the icon upload and removal routes, so an edited form never resets it. The icon column now holds
only a built-in key, so a custom URL is cleared.

Revision ID: 6d3a8f1c5e92
Revises: 2f6b9d4a8c15
Create Date: 2026-10-30 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d3a8f1c5e92"
down_revision: str | None = "2f6b9d4a8c15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: The built-in icon keys, as of this revision.
_BUILTIN_ICONS = ("authelia", "authentik", "casdoor", "keycloak", "pocketid")


def upgrade() -> None:
    """Add the uploaded-icon flag, false for every existing provider, and clear custom icon URLs."""
    op.add_column(
        "identity_providers",
        sa.Column(
            "icon_uploaded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Whether an uploaded icon is stored and shown instead of icon",
        ),
    )
    providers = sa.table("identity_providers", sa.column("icon", sa.String()))
    op.execute(providers.update().where(providers.c.icon.not_in(_BUILTIN_ICONS)).values(icon=None))


def downgrade() -> None:
    """Drop the uploaded-icon flag. The cleared custom icon URLs are not restored."""
    op.drop_column("identity_providers", "icon_uploaded")
