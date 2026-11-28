"""Delete the stored duplicate-activity notifications

v0.22 no longer stores an effort the user already has as a hidden duplicate, so nothing creates the
``duplicate_activity`` notification (``notifications.type`` 2) and the type is gone from the API. The upgrade deletes
the rows of that type, which would otherwise fail to read once the type is removed from the notification union. They
are inbox entries about activities that stay as they are.

The downgrade does nothing: the deleted rows cannot be recovered.

Revision ID: 6a1d9c4e7b25
Revises: 4f8c2b6d1a93
Create Date: 2026-11-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a1d9c4e7b25"
down_revision: str | None = "4f8c2b6d1a93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The stored integer of the retired ``duplicate_activity`` type.
_DUPLICATE_ACTIVITY = 2


def upgrade() -> None:
    """Delete every notification of the retired type."""
    op.execute(sa.text("DELETE FROM notifications WHERE type = :type").bindparams(type=_DUPLICATE_ACTIVITY))


def downgrade() -> None:
    """Do nothing: the deleted notifications cannot be recovered."""
