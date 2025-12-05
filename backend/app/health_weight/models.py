from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthWeight(Base):
    """
    SQLAlchemy model representing health weight measurements and body composition data.

    This model stores comprehensive health metrics including weight, BMI, and various
    body composition measurements for users. Each record is associated with a specific
    user and date.

    Attributes:
        id (int): Primary key, auto-incremented unique identifier.
        user_id (int): Foreign key referencing the user who owns this health weight record.
            Indexed for query performance. Cascades on delete.
        date (Date): The date when the health weight measurement was taken.
        weight (Decimal): Weight measurement in kilograms (precision: 10, scale: 2).
        bmi (Decimal, optional): Body Mass Index calculation (precision: 10, scale: 2).
        body_fat (Decimal, optional): Body fat percentage (precision: 10, scale: 2).
        body_water (Decimal, optional): Body hydration/water percentage (precision: 10, scale: 2).
        bone_mass (Decimal, optional): Bone mass percentage (precision: 10, scale: 2).
        muscle_mass (Decimal, optional): Muscle mass percentage (precision: 10, scale: 2).
        physique_rating (int, optional): Overall physique rating score.
        visceral_fat (Decimal, optional): Visceral fat rating (precision: 10, scale: 2).
        metabolic_age (int, optional): Calculated metabolic age.
        source (str, optional): Source or origin of the health weight data (max length: 250).

    Relationships:
        user (User): Many-to-one relationship with the User model. References the user
            who owns this health weight record.
    """

    __tablename__ = "health_weight"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_weight belongs",
    )
    date = Column(
        Date,
        nullable=False,
        comment="Health weight date (date)",
    )
    weight = Column(
        DECIMAL(precision=10, scale=2),
        nullable=False,
        comment="Weight in kg",
    )
    bmi = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Body mass index (BMI)",
    )
    body_fat = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Body fat percentage",
    )
    body_water = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Body hydration percentage",
    )
    bone_mass = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Bone mass percentage",
    )
    muscle_mass = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Muscle mass percentage",
    )
    physique_rating = Column(
        Integer,
        nullable=True,
        comment="Physique rating",
    )
    visceral_fat = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Visceral fat rating",
    )
    metabolic_age = Column(
        Integer,
        nullable=True,
        comment="Metabolic age",
    )
    source = Column(
        String(length=250), nullable=True, comment="Source of the health weight data"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_weight")
