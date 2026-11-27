"""Refresh token digests, CSRF removal and per-user Strava activity ids

The steps run in this order.

Store refresh tokens as keyed digests and end the sessions open before it
-------------------------------------------------------------------------

A session stored the Argon2 hash of its refresh token, and every refresh paid for a verify and a hash of 64 MiB each
while holding the session row. A refresh token is 256 bits of signed random data, so a session now stores an
HMAC-SHA256 digest of it, as rotated refresh tokens and CSRF tokens already do. A digest cannot be told from an
Argon2 hash, and the stored Argon2 hashes never match a digest, so the open sessions are deleted instead of left
unusable: every user signs in once more. Deleting a session deletes its rotated refresh tokens (foreign key with
``ON DELETE CASCADE``); the identity-provider tokens of those sessions, which have no foreign key, are revoked at the
provider by the scheduled sweep of ended sessions.

The downgrade has nothing to restore; the sessions the upgrade ended stay ended.

Drop the CSRF token hash of a session
-------------------------------------

The CSRF token was never checked by value on a route that mattered: a web client authenticates its requests with the
``Authorization`` header, and the one ambient credential, the refresh cookie, is read by two routes that now check
``Origin``. The token is gone, and so is the digest a session kept of it.

The downgrade adds the column back empty.

Scope the Strava activity ID of an activity to the user
-------------------------------------------------------

``activities.strava_activity_id`` was unique across the whole table, while an activity is deduplicated per user. A
second account linking the same Strava athlete hit the constraint on every activity it imported. Provider activities
are only ever looked up for their owner, so the global constraint is replaced by a plain index on
``(user_id, strava_activity_id)`` for that lookup. Which activities a user holds once is still the
``(user_id, dedup_key)`` index.

The old constraint was created unnamed, so it is found through the inspector.

The downgrade keeps the lowest-id holder of each Strava activity ID and clears the ID of every other holder, so the
restored constraint holds.

Revision ID: e95a7c1d4b36
Revises: 1087a5442836
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e95a7c1d4b36"
down_revision: str | None = "1087a5442836"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade_session_refresh_token_digest() -> None:
    """End every session, whose stored refresh-token hash would never match a digest."""
    op.execute("DELETE FROM users_sessions")


def downgrade_session_refresh_token_digest() -> None:
    """Do nothing: the sessions the upgrade ended stay ended."""


def upgrade_drop_session_csrf_token_hash() -> None:
    """Drop ``users_sessions.csrf_token_hash``."""
    op.drop_column("users_sessions", "csrf_token_hash")


def downgrade_drop_session_csrf_token_hash() -> None:
    """Add ``users_sessions.csrf_token_hash`` back, empty for every session."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "csrf_token_hash",
            sa.String(length=255),
            nullable=True,
            comment="Hashed CSRF token for refresh validation",
        ),
    )


_INDEX = "ix_activities_user_id_strava_activity_id"


def upgrade_activities_strava_activity_id_per_user() -> None:
    """Drop the table-wide unique constraint and index ``(user_id, strava_activity_id)``."""
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("activities"):
        if constraint["column_names"] == ["strava_activity_id"]:
            op.drop_constraint(constraint["name"], "activities", type_="unique")
    op.create_index(_INDEX, "activities", ["user_id", "strava_activity_id"])


def downgrade_activities_strava_activity_id_per_user() -> None:
    """Restore the table-wide unique constraint, clearing the ID of every holder but the lowest activity id."""
    op.drop_index(_INDEX, table_name="activities")
    op.execute(
        "UPDATE activities SET strava_activity_id = NULL WHERE id IN ("
        "SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY strava_activity_id ORDER BY id) AS position "
        "FROM activities WHERE strava_activity_id IS NOT NULL) AS holders WHERE position > 1)"
    )
    op.create_unique_constraint("activities_strava_activity_id_key", "activities", ["strava_activity_id"])


def upgrade() -> None:
    """Run every step in order."""
    upgrade_session_refresh_token_digest()
    upgrade_drop_session_csrf_token_hash()
    upgrade_activities_strava_activity_id_per_user()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_activities_strava_activity_id_per_user()
    downgrade_drop_session_csrf_token_hash()
    downgrade_session_refresh_token_digest()
