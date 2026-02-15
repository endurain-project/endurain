"""v0.18.0 Advanced Performance Metrics migration

Revision ID: a1b2c3d4e5f6
Revises: 262ec21a6c15
Create Date: 2026-02-07 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "262ec21a6c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add advanced performance metric columns to activities and activity_laps tables."""
    
    # Add FTP field to users table
    op.add_column(
        "users",
        sa.Column(
            "functional_threshold_power",
            sa.Integer(),
            nullable=True,
            comment="User Functional Threshold Power (FTP) in watts for advanced performance metrics",
        ),
    )
    
    # Add advanced performance metrics columns to activities table
    op.add_column(
        "activities",
        sa.Column(
            "intensity_factor",
            sa.DECIMAL(precision=10, scale=4),
            nullable=True,
            comment="Intensity Factor (IF) = NP / FTP",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "training_stress_score",
            sa.DECIMAL(precision=10, scale=2),
            nullable=True,
            comment="Training Stress Score (TSS)",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "variability_index",
            sa.DECIMAL(precision=10, scale=4),
            nullable=True,
            comment="Variability Index (VI) = NP / Average Power",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "efficiency_factor",
            sa.DECIMAL(precision=10, scale=4),
            nullable=True,
            comment="Efficiency Factor (EF) = NP / Average Heart Rate",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "aerobic_decoupling",
            sa.DECIMAL(precision=10, scale=2),
            nullable=True,
            comment="Aerobic Decoupling (%) = percentage difference in EF between ride halves",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "vam",
            sa.DECIMAL(precision=10, scale=2),
            nullable=True,
            comment="VAM (Velocità Ascensionale Media) in meters per hour",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "climbing_efficiency",
            sa.DECIMAL(precision=10, scale=4),
            nullable=True,
            comment="Climbing Efficiency = VAM / Power-to-weight ratio",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "gradient_distribution",
            sa.JSON(),
            nullable=True,
            comment="Gradient distribution histogram as percentage time spent at each grade",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "w_prime_balance",
            sa.JSON(),
            nullable=True,
            comment="W' Balance data including min balance and percent depleted",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "quadrant_analysis",
            sa.JSON(),
            nullable=True,
            comment="Quadrant analysis distribution of pedaling force vs. cadence",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "power_duration_curve",
            sa.JSON(),
            nullable=True,
            comment="Power duration curve with max power at various time windows",
        ),
    )
    


def downgrade() -> None:
    """Remove advanced performance metric columns from activities table."""
    
    # Remove columns from activities table
    op.drop_column("activities", "power_duration_curve")
    op.drop_column("activities", "quadrant_analysis")
    op.drop_column("activities", "w_prime_balance")
    op.drop_column("activities", "gradient_distribution")
    op.drop_column("activities", "climbing_efficiency")
    op.drop_column("activities", "vam")
    op.drop_column("activities", "aerobic_decoupling")
    op.drop_column("activities", "efficiency_factor")
    op.drop_column("activities", "variability_index")
    op.drop_column("activities", "training_stress_score")
    op.drop_column("activities", "intensity_factor")
    
    # Remove FTP field from users table
    op.drop_column("users", "functional_threshold_power")
