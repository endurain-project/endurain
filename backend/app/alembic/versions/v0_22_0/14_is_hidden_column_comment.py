"""Correct the is_hidden column comment

The ``activities.is_hidden`` comment named a duplicate activity waiting for the user's review, a state v0.22 no longer
creates: an import of an effort the user already has is merged into that activity. The column is the owner's choice to
hide the activity from everyone else. Only the comment changes; no data does.

The downgrade restores the previous comment.

Revision ID: 2b7e5f0c9d31
Revises: 6a1d9c4e7b25
Create Date: 2026-11-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b7e5f0c9d31"
down_revision: str | None = "6a1d9c4e7b25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREVIOUS = "Indicates if the activity is hidden (e.g., duplicate activity waiting to be reviewed by the user)"
_CURRENT = "Whether the owner hides the activity from everyone else"


def upgrade() -> None:
    """Comment ``is_hidden`` as the owner's choice to hide the activity."""
    op.alter_column(
        "activities",
        "is_hidden",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment=_CURRENT,
        existing_comment=_PREVIOUS,
    )


def downgrade() -> None:
    """Restore the duplicate-review comment on ``is_hidden``."""
    op.alter_column(
        "activities",
        "is_hidden",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        comment=_PREVIOUS,
        existing_comment=_CURRENT,
    )
