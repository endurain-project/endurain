"""2: rework followers model — surrogate id PK, followee_id rename, status enum, timestamps

Revision ID: a7f3c1e9d2b4
Revises: b3d9f1a7c2e4
Create Date: 2026-07-24 00:00:00.000000

Transforms the ``followers`` table from a composite (follower_id, following_id)
primary key with an ``is_accepted`` boolean into the modernised shape: a
surrogate ``id`` primary key, ``following_id`` renamed to ``followee_id``, an
extensible ``status`` string (backfilled ``accepted``/``pending``), UTC
``created_at``/``updated_at`` timestamps, and a unique(follower_id, followee_id)
constraint preserving one relationship per direction (previously the composite
PK). No backward compatibility — a straight data migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3c1e9d2b4"
down_revision: str | None = "b3d9f1a7c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Rename following_id -> followee_id (and its index).
    op.alter_column("followers", "following_id", new_column_name="followee_id")
    op.execute("ALTER INDEX ix_followers_following_id RENAME TO ix_followers_followee_id")

    # 2. Add the status column, backfill from is_accepted, then enforce NOT NULL.
    op.add_column("followers", sa.Column("status", sa.String(length=20), nullable=True))
    op.execute("UPDATE followers SET status = CASE WHEN is_accepted THEN 'accepted' ELSE 'pending' END")
    op.alter_column("followers", "status", nullable=False, server_default="pending")

    # 3. Drop the legacy is_accepted boolean.
    op.drop_column("followers", "is_accepted")

    # 4. Add server-maintained UTC timestamps.
    op.add_column(
        "followers",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "followers",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. Swap the composite (follower_id, following_id) primary key for a surrogate
    #    id. SERIAL auto-assigns ids to existing rows and creates the PK index.
    op.drop_constraint("followers_pkey", "followers", type_="primary")
    op.execute("ALTER TABLE followers ADD COLUMN id SERIAL PRIMARY KEY")

    # 6. Preserve one relationship per direction (previously enforced by the
    #    composite primary key).
    op.create_unique_constraint("uq_followers_follower_followee", "followers", ["follower_id", "followee_id"])


def downgrade() -> None:
    op.drop_constraint("uq_followers_follower_followee", "followers", type_="unique")
    # Dropping the surrogate id column also drops its primary key.
    op.drop_column("followers", "id")
    op.drop_column("followers", "updated_at")
    op.drop_column("followers", "created_at")

    # Restore the is_accepted boolean from status.
    op.add_column("followers", sa.Column("is_accepted", sa.Boolean(), nullable=True))
    op.execute("UPDATE followers SET is_accepted = (status = 'accepted')")
    op.alter_column("followers", "is_accepted", nullable=False)
    op.drop_column("followers", "status")

    # Rename followee_id back to following_id (and its index) and restore the
    # composite primary key.
    op.execute("ALTER INDEX ix_followers_followee_id RENAME TO ix_followers_following_id")
    op.alter_column("followers", "followee_id", new_column_name="following_id")
    op.create_primary_key("followers_pkey", "followers", ["follower_id", "following_id"])
