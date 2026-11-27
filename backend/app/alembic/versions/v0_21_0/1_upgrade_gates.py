"""Refuse an upgrade that cannot proceed

The steps run in this order.

Require the v0.20 data migrations to have finished
--------------------------------------------------

Endurain v0.21 upgrades only from a v0.20.x install whose data migrations have all run. The v0.20 data migrations
(1-6 and 8-10) rewrite user-owned rows (activities, streams, laps, media, photos, weights and users); their handlers
are gone from this release, so a row they would have rewritten stays as it is. The upgrade therefore refuses to
start while an install that holds users has a data migration pending, before the first commit of the v0.21 chain, so
the database stays at v0.20.x. A fresh install holds no users and passes. The schema does not change.

Refuse the upgrade while a provider uses a reserved slug
--------------------------------------------------------

The fixed words of the public identity-provider routes (``login``, ``callback``, ``icon`` and
``backchannel-logout``) cannot be a provider slug, since the same path would then name two routes. A provider that
already has one cannot be renamed silently: the callback URL registered at the provider names the slug. The upgrade
stops and names the slugs, and the administrator renames the provider (and registers the new callback URL at it)
before upgrading again. The schema does not change.

Revision ID: c5cfe02a11c2
Revises: d54bdd779392
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5cfe02a11c2"
down_revision: str | None = "d54bdd779392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The data migrations a v0.20.x install must have executed; migration 7 is registered executed on every install.
_DATA_MIGRATIONS = (1, 2, 3, 4, 5, 6, 8, 9, 10)


def upgrade_require_v0_20_data_migrations() -> None:
    """Refuse to continue while a v0.20 data migration has not finished on an install with users.

    Raises:
        RuntimeError: When a data migration is absent from the ``migrations`` table or not executed.
    """
    connection = op.get_bind()
    if not connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users)")).scalar_one():
        return
    statement = sa.text("SELECT id FROM migrations WHERE executed AND id IN :ids").bindparams(
        sa.bindparam("ids", expanding=True)
    )
    executed = {migration_id for (migration_id,) in connection.execute(statement, {"ids": list(_DATA_MIGRATIONS)})}
    missing = [migration_id for migration_id in _DATA_MIGRATIONS if migration_id not in executed]
    if missing:
        raise RuntimeError(
            f"Data migrations {', '.join(str(migration_id) for migration_id in missing)} have not finished. "
            "Endurain v0.21 upgrades only from a v0.20.x install whose data migrations have all finished. Start "
            "the latest v0.20.x release, let it run until every data migration is done, then upgrade again."
        )


def downgrade_require_v0_20_data_migrations() -> None:
    """Nothing to undo: the upgrade only checks."""


# The reserved words as of this revision; later words are enforced by the application, not re-checked here.
_RESERVED_SLUGS = ("backchannel-logout", "callback", "icon", "login")


def upgrade_reserved_identity_provider_slugs() -> None:
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


def downgrade_reserved_identity_provider_slugs() -> None:
    """Nothing to undo: the upgrade only checks."""


def upgrade() -> None:
    """Run every step in order."""
    upgrade_require_v0_20_data_migrations()
    upgrade_reserved_identity_provider_slugs()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_reserved_identity_provider_slugs()
    downgrade_require_v0_20_data_migrations()
