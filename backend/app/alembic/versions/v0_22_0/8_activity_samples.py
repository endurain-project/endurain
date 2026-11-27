"""Add the columnar ``activity_samples`` table

``activity_samples`` holds one row per activity: ``offsets_ms`` (each sample's time in milliseconds from the
activity's start time) and one nullable array per channel (latitude, longitude, elevation, heart rate, power, cadence,
speed, temperature), all aligned with ``offsets_ms``. It replaces the per-stream JSON waypoints of
``activities_streams``, which the v0.22 reprocess data migration converts; this revision only creates the table and
does not touch the old one.

CHECK constraints keep every present channel the length of ``offsets_ms`` and latitude and longitude together. Each
array column is stored with ``lz4`` compression, which PostgreSQL applies to values that go out of line.

The downgrade drops the table.

Revision ID: 3c1f5a7d9e24
Revises: 069908f3eab8
Create Date: 2026-11-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3c1f5a7d9e24"
down_revision: str | None = "069908f3eab8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "activity_samples"

#: Channel columns with their element type and unit comment.
_CHANNELS: tuple[tuple[str, sa.types.TypeEngine, str], ...] = (
    ("latitude", postgresql.DOUBLE_PRECISION(), "Latitude per sample, in degrees; NULL when the activity has no GPS"),
    ("longitude", postgresql.DOUBLE_PRECISION(), "Longitude per sample, in degrees; NULL when the activity has no GPS"),
    ("elevation", postgresql.REAL(), "Elevation per sample, in meters; NULL when the activity has none"),
    ("heart_rate", postgresql.REAL(), "Heart rate per sample, in bpm; NULL when the activity has none"),
    ("power", postgresql.REAL(), "Power per sample, in watts; NULL when the activity has none"),
    (
        "cadence",
        postgresql.REAL(),
        "Cadence per sample, in rpm (spm for running); NULL when the activity has none",
    ),
    ("speed", postgresql.REAL(), "Speed per sample, in m/s; NULL when the activity has none"),
    (
        "temperature",
        postgresql.REAL(),
        "Temperature per sample, in degrees Celsius; NULL when the activity has none",
    ),
)


def upgrade() -> None:
    """Create ``activity_samples`` with its CHECK constraints and set ``lz4`` compression on every array column."""
    op.create_table(
        _TABLE,
        sa.Column(
            "activity_id",
            sa.Uuid(),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            primary_key=True,
            comment="Activity the samples belong to",
        ),
        sa.Column(
            "offsets_ms",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            comment="Each sample's time in milliseconds from the activity start time; may be negative",
        ),
        *(
            sa.Column(name, postgresql.ARRAY(element), nullable=True, comment=comment)
            for name, element, comment in _CHANNELS
        ),
        *(
            sa.CheckConstraint(
                f"{name} IS NULL OR cardinality({name}) = cardinality(offsets_ms)", name=f"ck_{_TABLE}_{name}_len"
            )
            for name, _, _ in _CHANNELS
        ),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name=f"ck_{_TABLE}_lat_lon_together"),
    )
    for column in ("offsets_ms", *(name for name, _, _ in _CHANNELS)):
        op.execute(sa.text(f"ALTER TABLE {_TABLE} ALTER COLUMN {column} SET COMPRESSION lz4"))


def downgrade() -> None:
    """Drop ``activity_samples``."""
    op.drop_table(_TABLE)
