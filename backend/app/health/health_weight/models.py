from datetime import date as date_type
from decimal import Decimal
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class HealthWeight(Base):
    """
    User health weight and body composition data.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        date: Calendar date of the measurement.
        weight: Weight in kilograms.
        bmi: Body Mass Index.
        body_fat: Body fat percentage.
        body_water: Body hydration percentage.
        bone_mass: Bone mass percentage.
        muscle_mass: Muscle mass percentage.
        physique_rating: Physique rating score.
        visceral_fat: Visceral fat rating.
        metabolic_age: Calculated metabolic age.
        source: Data source.
        user: Relationship to Users model.
    """

    __tablename__ = "health_weight"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_weight belongs",
    )
    date: Mapped[date_type] = mapped_column(
        nullable=False,
        index=True,
        comment="Health weight date (date)",
    )
    weight: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        comment="Weight in kg",
    )
    bmi: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body mass index (BMI)",
    )
    body_fat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body fat percentage",
    )
    body_water: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body hydration percentage",
    )
    bone_mass: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Bone mass percentage",
    )
    muscle_mass: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Muscle mass percentage",
    )
    physique_rating: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Physique rating",
    )
    visceral_fat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Visceral fat rating",
    )
    metabolic_age: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Metabolic age",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health weight data",
    )

    # Define a relationship to the Users model
    # TODO: Change to Mapped["User"] when all modules use mapped
    users = relationship("Users", back_populates="health_weight")
