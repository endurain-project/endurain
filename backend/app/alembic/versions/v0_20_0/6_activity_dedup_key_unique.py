"""6: enforce activity dedup_key uniqueness per user

Revision ID: e4a1b8c73f26
Revises: b7c2e9d4a815
Create Date: 2026-07-27 00:00:00.000000

The ingestion service checks ``dedup_key`` before inserting, but that check is
read-then-write: two concurrent imports of the same file or provider activity can
both see "not found" and both insert. The bulk-import ThreadPoolExecutor and
durable-job retries make that a realistic race, not a theoretical one, so the
guarantee is moved into the database.

Existing duplicates are resolved **non-destructively**: no activity is deleted.
For each duplicated ``(user_id, dedup_key)`` group the lowest id keeps the key
and the rest have theirs set to NULL. Those rows remain fully intact and visible
to the athlete; they simply lose their idempotency key, so a future re-import
could recreate them. Deleting them here would destroy user data on the basis of a
key that was never guaranteed unique in the first place.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a1b8c73f26"
down_revision: str | None = "b7c2e9d4a815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clear the key on every duplicate except the earliest row in each group, so
    # the unique index below can be created. Rows are kept; only the key is
    # dropped. NULL keys are excluded because they are already unconstrained.
    op.execute(
        """
        UPDATE activities
        SET dedup_key = NULL
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id, dedup_key ORDER BY id
                       ) AS row_position
                FROM activities
                WHERE dedup_key IS NOT NULL
            ) ranked
            WHERE ranked.row_position > 1
        )
        """
    )

    # The composite index replaces the single-column one: every lookup is
    # "this key, for this owner" (``get_activity_by_dedup_key``), so the
    # standalone dedup_key index no longer earns its write cost.
    op.drop_index(op.f("ix_activities_dedup_key"), table_name="activities")
    op.create_index(
        "uq_activities_user_dedup_key",
        "activities",
        ["user_id", "dedup_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_activities_user_dedup_key", table_name="activities")
    op.create_index(op.f("ix_activities_dedup_key"), "activities", ["dedup_key"], unique=False)
