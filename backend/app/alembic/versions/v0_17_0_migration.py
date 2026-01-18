"""v0.17.0 migration - Add watch/computer gear type and computer_models table

Revision ID: 15f997232995
Revises: 215d794b3041
Create Date: 2026-01-18 12:00:00.000000

"""

import json
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "15f997232995"
down_revision: Union[str, None] = "215d794b3041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create computer_models table
    op.create_table(
        "computer_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "manufacturer",
            sa.String(length=50),
            nullable=False,
            comment="Manufacturer (garmin, suunto, etc.)",
        ),
        sa.Column(
            "product_code",
            sa.String(length=100),
            nullable=True,
            comment="Product code from FIT file (e.g., fenix7x, edge530)",
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            nullable=True,
            comment="Numeric product ID from FIT file",
        ),
        sa.Column(
            "model_name",
            sa.String(length=200),
            nullable=False,
            comment="Human-readable model name (e.g., Fenix 7X, Edge 530)",
        ),
        sa.Column(
            "region",
            sa.String(length=50),
            nullable=True,
            comment="Region variant (Asia, Japan, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_computer_models_manufacturer"),
        "computer_models",
        ["manufacturer"],
        unique=False,
    )
    op.create_index(
        op.f("ix_computer_models_product_code"),
        "computer_models",
        ["product_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_computer_models_product_id"),
        "computer_models",
        ["product_id"],
        unique=False,
    )

    # Add columns to gear table
    op.add_column(
        "gear",
        sa.Column(
            "serial_number",
            sa.String(length=100),
            nullable=True,
            comment="Serial number (for watch/computer gear type)",
        ),
    )
    op.add_column(
        "gear",
        sa.Column(
            "computer_model_id",
            sa.Integer(),
            nullable=True,
            comment="Reference to computer_models table (for watch/computer gear type)",
        ),
    )
    op.create_index(
        op.f("ix_gear_serial_number"), "gear", ["serial_number"], unique=False
    )
    op.create_index(
        op.f("ix_gear_computer_model_id"), "gear", ["computer_model_id"], unique=False
    )
    op.create_foreign_key(
        "fk_gear_computer_model_id",
        "gear",
        "computer_models",
        ["computer_model_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Seed Garmin models from JSON file
    data_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "computer_models",
        "data",
        "garmin_models.json",
    )
    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            garmin_models = json.load(f)

        # Build insert values
        computer_models_table = sa.table(
            "computer_models",
            sa.column("manufacturer", sa.String),
            sa.column("product_code", sa.String),
            sa.column("product_id", sa.Integer),
            sa.column("model_name", sa.String),
            sa.column("region", sa.String),
        )

        op.bulk_insert(
            computer_models_table,
            [
                {
                    "manufacturer": m.get("manufacturer", "garmin"),
                    "product_code": m.get("product_code"),
                    "product_id": m.get("product_id"),
                    "model_name": m.get("model_name"),
                    "region": m.get("region"),
                }
                for m in garmin_models
            ],
        )


def downgrade() -> None:
    # Remove foreign key and columns from gear table
    op.drop_constraint("fk_gear_computer_model_id", "gear", type_="foreignkey")
    op.drop_index(op.f("ix_gear_computer_model_id"), table_name="gear")
    op.drop_index(op.f("ix_gear_serial_number"), table_name="gear")
    op.drop_column("gear", "computer_model_id")
    op.drop_column("gear", "serial_number")

    # Drop computer_models table
    op.drop_index(op.f("ix_computer_models_product_id"), table_name="computer_models")
    op.drop_index(op.f("ix_computer_models_product_code"), table_name="computer_models")
    op.drop_index(op.f("ix_computer_models_manufacturer"), table_name="computer_models")
    op.drop_table("computer_models")
