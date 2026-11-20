"""Refuse an upgrade that cannot proceed

The steps run in this order.

Require the v0.21 data migrations to have finished
--------------------------------------------------

Endurain v0.22 upgrades only from a v0.21.x install whose data migrations have all run. The v0.21 data migrations
(11-14) rewrite stored files and shared state after the UUID conversion; their handlers are gone from this release,
so a file they would have renamed stays as it is. The upgrade therefore refuses to start while an install that holds
users has a data migration pending. A fresh install holds no users and passes. The schema does not change.

A database older than v0.21 never reaches this revision: the startup pre-flight in ``migrations.startup`` refuses it
before any revision runs.

Revision ID: b6cf67a93d94
Revises: e95a7c1d4b36
Create Date: 2026-11-19 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6cf67a93d94"
down_revision: str | None = "e95a7c1d4b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The data migrations a v0.21.x install must have executed.
_DATA_MIGRATIONS = (11, 12, 13, 14)


def upgrade_require_v0_21_data_migrations() -> None:
    """Refuse to continue while a v0.21 data migration has not finished on an install with users.

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
            "Endurain v0.22 upgrades only from a v0.21.x install whose data migrations have all finished. Start "
            "the latest v0.21.x release, let it run until every data migration is done, then upgrade again."
        )


def downgrade_require_v0_21_data_migrations() -> None:
    """Nothing to undo: the upgrade only checks."""


def upgrade() -> None:
    """Run every step in order."""
    upgrade_require_v0_21_data_migrations()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_require_v0_21_data_migrations()
