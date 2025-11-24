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
    garminconnect_body_composition_id = Column(
        String(length=45), nullable=True, comment="Garmin Connect body composition ID"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_weight")
