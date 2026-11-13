"""80: refuse the upgrade while a provider uses a reserved slug

The fixed words of the public identity-provider routes (``login``, ``callback``, ``icon`` and
``backchannel-logout``) cannot be a provider slug, since the same path would then name two routes. A provider that
already has one cannot be renamed silently: the callback URL registered at the provider names the slug. The upgrade
stops and names the slugs, and the administrator renames the provider (and registers the new callback URL at it)
before upgrading again. The schema does not change.

Revision ID: d80f4b6c2e93
Revises: c79e3a5d1b82
Create Date: 2026-11-11 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d80f4b6c2e93"
down_revision: str | None = "c79e3a5d1b82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The reserved words as of this revision; later words are enforced by the application, not re-checked here.
_RESERVED_SLUGS = ("backchannel-logout", "callback", "icon", "login")


def upgrade() -> None:
    """Refuse to continue while a provider uses a reserved slug.

    Raises:
        RuntimeError: When one or more providers have a reserved slug.
    """
    statement = sa.text("SELECT slug FROM identity_providers WHERE slug IN :slugs ORDER BY slug").bindparams(
        sa.bindparam("slugs", expanding=True)
    )
    used = [slug for (slug,) in op.get_bind().execute(statement, {"slugs": list(_RESERVED_SLUGS)})]
    if used:
        raise RuntimeError(
            "Cannot upgrade: identity provider slugs cannot be the words the sign-in routes use "
            f"({', '.join(_RESERVED_SLUGS)}). Providers using one: {', '.join(used)}. Change the slug of each "
            "of them, register the new callback URL "
            "(<ENDURAIN_HOST>/api/v1/public/idp/callback/<slug>) at the provider, then upgrade again."
        )


def downgrade() -> None:
    """Nothing to undo: the upgrade only checks."""
