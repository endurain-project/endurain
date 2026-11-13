"""71: move each user's TOTP secret from users_mfa to mfa_factors

``mfa_factors`` holds one row per enrolled second factor, so a factor type that is not a TOTP secret can be added
without another table. Every enabled ``users_mfa`` row becomes a ``totp`` factor with the same ciphertext, so no
secret is re-encrypted, and ``users_mfa`` is dropped.

The downgrade recreates ``users_mfa`` with a row for every user, enabled where the user has a TOTP factor, and drops
``mfa_factors``.

Revision ID: a71e4c9d2b60
Revises: a70d3b8e5f19
Create Date: 2026-11-10 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a71e4c9d2b60"
down_revision: str | None = "a70d3b8e5f19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mfa_factors"


def upgrade() -> None:
    """Create ``mfa_factors`` and copy the enabled TOTP secrets into it."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="FK to users"),
        sa.Column("type", sa.String(length=16), nullable=False, comment="Factor type: totp"),
        sa.Column("credential", sa.String(length=512), nullable=False, comment="Fernet-encrypted factor secret"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="When the factor was enrolled"),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the factor last verified a sign-in or step-up",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("type IN ('totp')", name="ck_mfa_factors_type"),
    )
    op.create_index("ix_mfa_factors_user_id", _TABLE, ["user_id"])
    op.create_index(
        "uq_mfa_factors_user_totp",
        _TABLE,
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("type = 'totp'"),
    )
    op.execute(
        sa.text(
            "INSERT INTO mfa_factors (user_id, type, credential, created_at) "
            "SELECT user_id, 'totp', mfa_secret, CURRENT_TIMESTAMP FROM users_mfa "
            "WHERE mfa_enabled AND mfa_secret IS NOT NULL"
        )
    )
    op.drop_table("users_mfa")


def downgrade() -> None:
    """Recreate ``users_mfa`` from the factors and drop ``mfa_factors``."""
    op.create_table(
        "users_mfa",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="FK to users — one row per user"),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, comment="Whether TOTP MFA is active for this user"),
        sa.Column("mfa_secret", sa.String(length=512), nullable=True, comment="Fernet-encrypted TOTP secret"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_users_mfa_user_id"),
    )
    op.create_index("ix_users_mfa_user_id", "users_mfa", ["user_id"])
    op.execute(
        sa.text(
            "INSERT INTO users_mfa (user_id, mfa_enabled, mfa_secret) "
            "SELECT u.id, f.credential IS NOT NULL, f.credential FROM users u "
            "LEFT JOIN mfa_factors f ON f.user_id = u.id AND f.type = 'totp'"
        )
    )
    op.drop_index("uq_mfa_factors_user_totp", table_name=_TABLE)
    op.drop_index("ix_mfa_factors_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
