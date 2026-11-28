"""Add the activity sources table and fill it from the idempotency keys and provider ids

``activity_sources`` holds one row per source an activity came from: a Strava or Garmin Connect activity id, or the
SHA-256 of an imported file. A user holds each identity once (two unique indexes), so importing the same activity
again is a no-op; ``session_start`` tells apart the activities of one multi-activity file, which share a hash and a
Garmin id. It replaces ``activities.dedup_key``, which nothing reads or writes after this release, and the provider id
columns, which are written but no longer read; both go in a later release.

The upgrade converts what exists. Every activity, a multisport leg included, keeps the identity its ``dedup_key``
named: a multisport parent has the whole file (no start) and each leg its session (with its start):

- ``strava:<id>`` becomes a Strava source (precedence 0, the API).
- ``garmin:<id>`` and ``garmin:<id>:<start>`` become a Garmin source (precedence 2, a device file), with the start when
  the key has one.
- ``file:<sha256>`` and ``file:<sha256>:<start>`` become a file source with the start when the key has one. The
  precedence is 2, a device file, for every converted file source: the file's format is not known until its file is
  adopted, and a source that is taken for a device file is never replaced by a later import.
- An activity that has a provider id and no source of that kind, one restored from a profile archive, gets a source
  from the column; a leg's carries the leg's start, as a leg's key did.

Rows already hidden as start-time duplicates are converted like any other. The downgrade rebuilds ``dedup_key`` from
the oldest source of every activity that has none, so an older release identifies them again, and drops the table.

Revision ID: 9e3b7a2c5d18
Revises: 7d4a9c1e6b52
Create Date: 2026-11-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e3b7a2c5d18"
down_revision: str | None = "7d4a9c1e6b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = "id, activity_id, user_id, kind, provider_id, file_sha256, session_start, precedence, received_at"

#: The three key shapes, each as a ``SELECT`` over the activities that are not a leg.
_FROM_STRAVA_KEY = """
SELECT gen_random_uuid(), id, user_id, 'strava', split_part(dedup_key, ':', 2)::bigint, NULL::varchar,
       NULL::timestamptz, 0, created_at
  FROM activities
 WHERE dedup_key ~ '^strava:[0-9]+$'
"""
_FROM_GARMIN_KEY = """
SELECT gen_random_uuid(), id, user_id, 'garmin', split_part(dedup_key, ':', 2)::bigint, NULL::varchar,
       CASE WHEN split_part(dedup_key, ':', 3) <> '' THEN to_timestamp(split_part(dedup_key, ':', 3)::bigint) END,
       2, created_at
  FROM activities
 WHERE dedup_key ~ '^garmin:[0-9]+(:[0-9]+)?$'
"""
_FROM_FILE_KEY = """
SELECT gen_random_uuid(), id, user_id, 'file', NULL::bigint, split_part(dedup_key, ':', 2),
       CASE WHEN split_part(dedup_key, ':', 3) <> '' THEN to_timestamp(split_part(dedup_key, ':', 3)::bigint) END,
       2, created_at
  FROM activities
 WHERE dedup_key ~ '^file:[0-9a-f]{64}(:[0-9]+)?$'
"""


def _from_provider_column(column: str, kind: str, precedence: int) -> str:
    """Build the conversion of a provider id column for the activities that have no source of that kind.

    Args:
        column: The ``activities`` column holding the provider id.
        kind: The source kind the column stands for.
        precedence: The precedence of that kind.

    Returns:
        An ``INSERT`` statement. ``DISTINCT ON`` keeps one activity per provider id, the oldest, because activities
        restored from an archive more than once can share an id; ``ON CONFLICT DO NOTHING`` leaves an id a key
        conversion already stored.
    """
    return f"""
INSERT INTO activity_sources ({_COLUMNS})
SELECT DISTINCT ON (a.user_id, a.{column}, a.session_start)
       gen_random_uuid(), a.id, a.user_id, '{kind}', a.{column}, NULL, a.session_start, {precedence}, a.created_at
  FROM (
        SELECT activities.*,
               CASE WHEN parent_activity_id IS NOT NULL THEN date_trunc('second', start_time) END AS session_start
          FROM activities
       ) a
 WHERE a.{column} IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM activity_sources s WHERE s.activity_id = a.id AND s.kind = '{kind}')
 ORDER BY a.user_id, a.{column}, a.session_start, a.created_at, a.id
ON CONFLICT DO NOTHING
"""  # noqa: S608


def upgrade() -> None:
    """Create ``activity_sources`` and convert the keys and provider ids into rows."""
    op.create_table(
        "activity_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "activity_id",
            sa.Uuid(),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
            comment="Activity the source belongs to",
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="User ID that owns the activity",
        ),
        sa.Column("kind", sa.String(length=16), nullable=False, comment="file, garmin or strava"),
        sa.Column(
            "provider_id",
            sa.BigInteger(),
            nullable=True,
            comment="Provider activity ID, for a garmin or strava source",
        ),
        sa.Column(
            "file_sha256", sa.String(length=64), nullable=True, comment="Hex SHA-256 of the file, for a file source"
        ),
        sa.Column(
            "session_start",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Start of the recording in whole seconds; null for a whole file and for a Strava activity",
        ),
        sa.Column(
            "precedence",
            sa.SmallInteger(),
            nullable=False,
            comment="2 device file, 1 generic file, 0 Strava API; the higher is the better record",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the source reached the activity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('file', 'garmin', 'strava')", name="ck_activity_sources_kind"),
        sa.CheckConstraint("num_nonnulls(provider_id, file_sha256) = 1", name="ck_activity_sources_one_identity"),
    )
    op.create_index(
        "uq_activity_sources_provider",
        "activity_sources",
        ["user_id", "kind", "provider_id", "session_start"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("provider_id IS NOT NULL"),
    )
    op.create_index(
        "uq_activity_sources_file",
        "activity_sources",
        ["user_id", "file_sha256", "session_start"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("file_sha256 IS NOT NULL"),
    )
    op.create_index("ix_activity_sources_activity_id_kind", "activity_sources", ["activity_id", "kind"])

    for conversion in (_FROM_STRAVA_KEY, _FROM_GARMIN_KEY, _FROM_FILE_KEY):
        op.execute(sa.text(f"INSERT INTO activity_sources ({_COLUMNS}) {conversion} ON CONFLICT DO NOTHING"))
    op.execute(sa.text(_from_provider_column("strava_activity_id", "strava", 0)))
    op.execute(sa.text(_from_provider_column("garminconnect_activity_id", "garmin", 2)))


def downgrade() -> None:
    """Rebuild ``dedup_key`` for the activities that have none, then drop ``activity_sources``."""
    op.execute(
        sa.text(
            """
UPDATE activities a
   SET dedup_key = oldest.key
  FROM (
        SELECT DISTINCT ON (activity_id) activity_id,
               CASE kind
                    WHEN 'strava' THEN 'strava:' || provider_id::text
                    WHEN 'garmin' THEN 'garmin:' || provider_id::text
                         || COALESCE(':' || extract(epoch FROM session_start)::bigint::text, '')
                    ELSE 'file:' || file_sha256
                         || COALESCE(':' || extract(epoch FROM session_start)::bigint::text, '')
               END AS key
          FROM activity_sources
         ORDER BY activity_id, received_at, id
       ) oldest
 WHERE a.id = oldest.activity_id
   AND a.dedup_key IS NULL
   AND NOT EXISTS (SELECT 1 FROM activities b WHERE b.user_id = a.user_id AND b.dedup_key = oldest.key)
"""
        )
    )
    op.drop_table("activity_sources")
