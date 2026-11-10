"""73: stamp each known device with the security generation and describe it

A known device counts only while its stamp equals the account's current security generation, so a security change
makes every device unknown at once. Existing rows are stamped with their user's current generation, so the upgrade
forgets no device and sends no new-device email for a device the user already signed in from; a user without a
generation row is at generation 0, the column's backfill default. ``browser``, ``operating_system`` and
``device_type`` let the user recognise a device in the list; existing rows keep them null until the device signs
in again.

Revision ID: c73a6e1b4d92
Revises: b72f5d0a3c81
Create Date: 2026-11-10 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c73a6e1b4d92"
down_revision: str | None = "b72f5d0a3c81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "auth_known_devices"


def upgrade() -> None:
    """Add the generation stamp, backfilled from the account's generation, and the description columns."""
    op.add_column(
        _TABLE,
        sa.Column(
            "security_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Account security generation the device was registered under; stale once a security change follows",
        ),
    )
    op.execute(
        "UPDATE auth_known_devices SET security_generation = account_security_generations.generation "
        "FROM account_security_generations WHERE account_security_generations.user_id = auth_known_devices.user_id"
    )
    op.alter_column(_TABLE, "security_generation", server_default=None)
    op.add_column(
        _TABLE,
        sa.Column(
            "browser", sa.String(length=45), nullable=True, comment="Browser of the last sign-in from the device"
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "operating_system",
            sa.String(length=45),
            nullable=True,
            comment="Operating system of the last sign-in from the device",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "device_type",
            sa.String(length=45),
            nullable=True,
            comment="Device type of the last sign-in from the device",
        ),
    )


def downgrade() -> None:
    """Drop the columns."""
    op.drop_column(_TABLE, "device_type")
    op.drop_column(_TABLE, "operating_system")
    op.drop_column(_TABLE, "browser")
    op.drop_column(_TABLE, "security_generation")
