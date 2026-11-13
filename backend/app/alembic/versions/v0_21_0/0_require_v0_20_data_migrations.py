"""0: require the v0.20 data migrations to have finished

Endurain v0.21 upgrades only from a v0.20.x install whose data migrations have all run. The v0.20 data migrations
(1-6 and 8-10) rewrite user-owned rows (activities, streams, laps, media, photos, weights and users); their handlers
are gone from this release, so a row they would have rewritten stays as it is. The upgrade therefore refuses to
start while an install that holds users has a data migration pending, before the first commit of the v0.21 chain, so
the database stays at v0.20.x. A fresh install holds no users and passes. The schema does not change.

Revision ID: c5cfe02a11c2
Revises: d54bdd779392
Create Date: 2026-11-12 09:00:00.000000

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


def upgrade() -> None:
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


def downgrade() -> None:
    """Nothing to undo: the upgrade only checks."""
