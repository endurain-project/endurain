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


class HealthData(Base):
    __tablename__ = "health_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_data belongs",
    )
    date = Column(
        Date,
        nullable=False,
        comment="Health data creation date (date)",
    )
    weight = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Weight in kg",
    )
    bmi = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Body mass index (BMI)",
    )
    # body_fat = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Body fat percentage",
    # )
    # body_water = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Body hydration percentage",
    # )
    # bone_mass = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Bone mass percentage",
    # )
    # muscle_mass = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Muscle mass percentage",
    # )
    # physique_rating = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Physique rating",
    # )
    # visceral_fat = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Visceral fat rating",
    # )
    # metabolic_age = Column(
    #     DECIMAL(precision=10, scale=2),
    #     nullable=True,
    #     comment="Metabolic age",
    # )
    garminconnect_body_composition_id = Column(
        String(length=45), nullable=True, comment="Garmin Connect body composition ID"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_data")
