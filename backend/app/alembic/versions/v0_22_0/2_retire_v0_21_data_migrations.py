"""Retire the v0.21 data migrations

The handlers of data migrations 11-14 (storage layout, image metadata, stored file names and shared state) are
removed, and with them the runner that executed the data migrations, so the ``migrations`` table that tracked them
goes. The upgrade source is v0.21.x, which revision 1 enforces: it reads that table and refuses while one of them is
pending.

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
    """Drop the data migration tracking table and the UUID conversion id mapping table."""
    op.execute(sa.text("DROP TABLE migrations"))
    op.execute(sa.text("DROP TABLE IF EXISTS uuid_migration_ids"))


def downgrade() -> None:
    """Refuse to downgrade.

    Raises:
        NotImplementedError: Always; the dropped tables cannot be rebuilt.
    """
    raise NotImplementedError(
        "Retiring the data migrations cannot be reversed: restore the database from the backup taken before "
        "the upgrade."
    )
