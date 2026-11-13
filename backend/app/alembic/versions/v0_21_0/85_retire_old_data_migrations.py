"""85: retire the v0.20 data migrations

The handlers of data migrations 1-6 and 8-10 are removed, so their rows leave the ``migrations`` table. The upgrade
source is v0.20.x, which revision 0 enforces: it refuses while one of them is pending. Row 7 stays, since it is
executed on every install.

Revision 66 never ran in production, so ``cadence_spm_migration_rows``, the bookkeeping table of its downgrade,
goes too.

The UUID conversion revisions that follow are the one-time exception to the events guide's rule to raise a payload
class's ``SCHEMA_VERSION``: they rewrite the integer ids inside stored event payloads in place and keep every
payload class's version. After the rewrite no integer-shaped payload remains, and every process is stopped during the
upgrade, so no old build can publish one.

The revision is irreversible.

Revision ID: b41c0afdc9d9
Revises: b84e9f3a6c25
Create Date: 2026-11-12 09:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b41c0afdc9d9"
down_revision: str | None = "b84e9f3a6c25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Delete the retired data migration rows and drop the revision 66 bookkeeping table."""
    op.execute(sa.text("DELETE FROM migrations WHERE id IN (1, 2, 3, 4, 5, 6, 8, 9, 10)"))
    op.execute(sa.text("DROP TABLE cadence_spm_migration_rows"))


def downgrade() -> None:
    """Refuse to downgrade.

    Raises:
        NotImplementedError: Always; the deleted rows and the dropped table cannot be rebuilt.
    """
    raise NotImplementedError(
        "Revision 85 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
