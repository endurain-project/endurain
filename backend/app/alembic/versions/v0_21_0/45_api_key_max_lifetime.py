"""45: cap the lifetime of API keys

Adds ``api_key_max_lifetime_days`` to ``server_settings`` and gives every API key that never expires an
expiry of 365 days from now, the setting's default, whatever the setting is. A key that already has an
expiry, including one in the past, is left as it is. ``users_api_keys.expires_at`` is then required.

Revision ID: c7e1f3a9d245
Revises: b5d8e2a4c371
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e1f3a9d245"
down_revision: str | None = "b5d8e2a4c371"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the setting, backfill the keys that never expire and require an expiry."""
    op.add_column(
        "server_settings",
        sa.Column(
            "api_key_max_lifetime_days",
            sa.Integer(),
            server_default=sa.text("365"),
            nullable=False,
            comment="Longest lifetime of a new API key, and its default, in days",
        ),
    )
    op.create_check_constraint(
        "api_key_max_lifetime_days_check", "server_settings", "api_key_max_lifetime_days BETWEEN 1 AND 3650"
    )
    op.execute("UPDATE users_api_keys SET expires_at = now() + interval '365 days' WHERE expires_at IS NULL")
    op.alter_column(
        "users_api_keys",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_comment="Key expiration timestamp (NULL = no expiry)",
        comment="Key expiration timestamp",
    )


def downgrade() -> None:
    """Allow keys without an expiry again and drop the setting."""
    op.alter_column(
        "users_api_keys",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_comment="Key expiration timestamp",
        comment="Key expiration timestamp (NULL = no expiry)",
    )
    op.drop_constraint("api_key_max_lifetime_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "api_key_max_lifetime_days")
