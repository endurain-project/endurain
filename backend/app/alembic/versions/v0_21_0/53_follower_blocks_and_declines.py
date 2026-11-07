"""53: add follower_blocks and follow_request_declines

``follower_blocks`` holds each user's block list: a blocked user cannot request to follow the blocker.
``follow_request_declines`` holds when a follow request was last declined, since declining deletes the request, so the
requester can be refused for seven days. Both tables start empty.

Revision ID: e4a7c2b9d150
Revises: c3d9a5e1f478
Create Date: 2026-11-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7c2b9d150"
down_revision: str | None = "c3d9a5e1f478"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the two tables with their unique pairs and the indexes the lookups use."""
    op.create_table(
        "follower_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False, comment="ID of the user who blocked"),
        sa.Column("blocked_id", sa.Integer(), nullable=False, comment="ID of the user who is blocked"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_follower_blocks_not_self"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_follower_blocks_blocker_blocked"),
    )
    op.create_index("ix_follower_blocks_id", "follower_blocks", ["id"], unique=False)
    op.create_index("ix_follower_blocks_blocker_id", "follower_blocks", ["blocker_id"], unique=False)
    op.create_index("ix_follower_blocks_blocked_id", "follower_blocks", ["blocked_id"], unique=False)

    op.create_table(
        "follow_request_declines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "follower_id", sa.Integer(), nullable=False, comment="ID of the requester whose request was declined"
        ),
        sa.Column("followee_id", sa.Integer(), nullable=False, comment="ID of the user who declined the request"),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=False, comment="When the request was declined"),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "followee_id", name="uq_follow_request_declines_follower_followee"),
    )
    op.create_index("ix_follow_request_declines_follower_id", "follow_request_declines", ["follower_id"], unique=False)
    op.create_index("ix_follow_request_declines_followee_id", "follow_request_declines", ["followee_id"], unique=False)


def downgrade() -> None:
    """Drop both tables, with the blocks and declines they hold."""
    op.drop_index("ix_follow_request_declines_followee_id", table_name="follow_request_declines")
    op.drop_index("ix_follow_request_declines_follower_id", table_name="follow_request_declines")
    op.drop_table("follow_request_declines")
    op.drop_index("ix_follower_blocks_blocked_id", table_name="follower_blocks")
    op.drop_index("ix_follower_blocks_blocker_id", table_name="follower_blocks")
    op.drop_index("ix_follower_blocks_id", table_name="follower_blocks")
    op.drop_table("follower_blocks")
