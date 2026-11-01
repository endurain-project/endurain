"""27: name each OAuth state's flow and carry a step-up's session and action

The callback read a state's flow from whether it had a user: a link had one, a login did not. A step-up
re-authentication also starts from a signed-in user, so a state now names its flow in ``purpose``, and a
step-up state records the session that started it and the operation it authorises.

Existing rows are short-lived and keep the flow they had: ``link`` when they carry a user, ``login``
otherwise.

Revision ID: 3e7c1a9d5b42
Revises: 9d2b6e4a7c15
Create Date: 2026-10-30 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e7c1a9d5b42"
down_revision: str | None = "9d2b6e4a7c15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the flow, the step-up session and the step-up action."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "purpose",
            sa.String(length=16),
            nullable=True,
            comment="Flow the state belongs to: login, link or step_up",
        ),
    )
    op.execute(sa.text("UPDATE oauth_states SET purpose = CASE WHEN user_id IS NULL THEN 'login' ELSE 'link' END"))
    op.alter_column("oauth_states", "purpose", existing_type=sa.String(length=16), nullable=False)
    op.add_column(
        "oauth_states",
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=True,
            comment="Session that started a step-up flow (step-up only)",
        ),
    )
    op.add_column(
        "oauth_states",
        sa.Column(
            "action",
            sa.String(length=32),
            nullable=True,
            comment="Sensitive operation a step-up flow authorises (step-up only)",
        ),
    )
    op.alter_column(
        "oauth_states",
        "browser_binding_hash",
        existing_type=sa.String(length=64),
        existing_nullable=True,
        comment="SHA-256 of the browser-binding cookie (link and step-up flows)",
        existing_comment="SHA-256 of the link's browser-binding cookie (link mode only)",
    )


def downgrade() -> None:
    """Drop the flow, the step-up session and the step-up action."""
    op.alter_column(
        "oauth_states",
        "browser_binding_hash",
        existing_type=sa.String(length=64),
        existing_nullable=True,
        comment="SHA-256 of the link's browser-binding cookie (link mode only)",
        existing_comment="SHA-256 of the browser-binding cookie (link and step-up flows)",
    )
    op.execute(sa.text("DELETE FROM oauth_states WHERE purpose = 'step_up'"))
    op.drop_column("oauth_states", "action")
    op.drop_column("oauth_states", "session_id")
    op.drop_column("oauth_states", "purpose")
