"""51: put the unit in the name of the health columns

Weight, body composition, sleep oxygen saturation and the health targets named their unit only in a comment.
The wire names now carry it (``weight_kg``, ``body_fat_percent``, ``sleep_seconds``), and the columns are
renamed so the ORM and the API agree. The values are unchanged.

Revision ID: b8c1f4a7d936
Revises: e5b7a3d9c142
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c1f4a7d936"
down_revision: str | None = "e5b7a3d9c142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``(table, old name, new name, new comment)`` for every renamed column.
_RENAMES = (
    ("health_weight", "weight", "weight_kg", "Weight in kg"),
    ("health_weight", "body_fat", "body_fat_percent", "Body fat percentage"),
    ("health_weight", "body_water", "body_water_percent", "Body hydration percentage"),
    ("health_weight", "bone_mass", "bone_mass_kg", "Bone mass in kg"),
    ("health_weight", "muscle_mass", "muscle_mass_kg", "Muscle mass in kg"),
    ("health_targets", "weight", "weight_kg", "Weight in kg"),
    ("health_targets", "sleep", "sleep_seconds", "Target sleep duration in seconds"),
    ("health_targets", "fasting", "fasting_seconds", "Target fasting duration in seconds"),
    ("health_sleep", "avg_spo2", "avg_spo2_percent", "Average SpO2 oxygen saturation percentage"),
    ("health_sleep", "lowest_spo2", "lowest_spo2_percent", "Lowest SpO2 reading during sleep"),
    ("health_sleep", "highest_spo2", "highest_spo2_percent", "Highest SpO2 reading during sleep"),
)


def upgrade() -> None:
    """Rename the columns."""
    for table, old, new, comment in _RENAMES:
        op.alter_column(table, old, new_column_name=new, comment=comment)


def downgrade() -> None:
    """Restore the old column names; the comments keep their new wording."""
    for table, old, new, comment in _RENAMES:
        op.alter_column(table, new, new_column_name=old, comment=comment)
