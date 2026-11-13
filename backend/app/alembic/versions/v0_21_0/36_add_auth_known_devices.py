"""36: add auth_known_devices for new-device sign-in notices

Each row is a browser a user signed in from, named by the SHA-256 hex digest of the device id its cookie holds,
never the id itself. A sign-in from a device the user has no row for sends a notice. The table starts empty, so the
first sign-in of each user after the upgrade registers a device without one.

Revision ID: d0aa98611b9c
Revises: 9e4b7a2d6c18
Create Date: 2026-11-01 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0aa98611b9c"
down_revision: str | None = "9e4b7a2d6c18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "auth_known_devices"
_PRUNE_INDEX = "ix_auth_known_devices_last_seen_at"


def upgrade() -> None:
    """Create ``auth_known_devices`` with its per-user unique device and the index the prune filters on."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User who signed in from the device"),
        sa.Column(
            "device_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex digest of the device id held in the browser's cookie",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="First sign-in from the device"),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Last sign-in from the device; the row is pruned 400 days after it",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_hash", name="uq_auth_known_devices_user_id_device_hash"),
    )
    op.create_index(_PRUNE_INDEX, _TABLE, ["last_seen_at"], unique=False)


def downgrade() -> None:
    """Drop ``auth_known_devices``."""
    op.drop_index(_PRUNE_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
