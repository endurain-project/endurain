"""Retire the v0.21 data migrations

The handlers of data migrations 11-14 (storage layout, image metadata, stored file names and shared state) are
removed, so their rows leave the ``migrations`` table. The upgrade source is v0.21.x, which revision 1 enforces: it
refuses while one of them is pending. Row 7, the v0.19.0 HR-zone backfill that every install registers as executed
and that has no handler, goes with them, so the table holds only migrations a later release adds.

``uuid_migration_ids``, the table the UUID conversion revisions fill and data migration 13 drops once the stored files
are renamed, goes too. It is already gone on an install that ran migration 13.

The revision is irreversible.

Revision ID: 50ac9225ce4f
Revises: b6cf67a93d94
Create Date: 2026-11-19 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50ac9225ce4f"
down_revision: str | None = "b6cf67a93d94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Delete the retired data migration rows and drop the UUID conversion id mapping table."""
    op.execute(sa.text("DELETE FROM migrations WHERE id IN (7, 11, 12, 13, 14)"))
    op.execute(sa.text("DROP TABLE IF EXISTS uuid_migration_ids"))


def downgrade() -> None:
    """Refuse to downgrade.

    Raises:
        NotImplementedError: Always; the deleted rows and the dropped table cannot be rebuilt.
    """
    raise NotImplementedError(
        "Retiring the data migrations cannot be reversed: restore the database from the backup taken before "
        "the upgrade."
    )
