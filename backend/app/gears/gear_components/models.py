from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

import gears.gear_components.schema as gear_components_schema

from core.database import Base


# Data model for gear table using SQLAlchemy's ORM
class GearComponents(Base):
    __tablename__ = "gear_components"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the gear component belongs to",
    )
    gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Gear ID associated with this component",
    )
    type = Column(
        String(length=250),
        nullable=False,
        comment="Type of gear component",
    )
    brand = Column(
        String(length=250),
        nullable=False,
        comment="Gear component brand (May include spaces)",
    )
    model = Column(
        String(length=250),
        nullable=False,
        comment="Gear component model (May include spaces)",
    )
    purchase_date = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Gear component purchase date (DateTime)",
    )
    retired_date = Column(
        DateTime,
        nullable=True,
        comment="Gear component retired date (DateTime)",
    )
    active = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the gear component is active (true - yes, false - no)",
    )
    expected_kms = Column(
        Integer,
        nullable=True,
        comment="Expected kilometers of the gear component",
    )
    purchase_value = Column(
        DECIMAL(precision=11, scale=2),
        nullable=True,
        comment="Purchase value of the gear component",
    )

    # Define a relationship to the Users model
    users = relationship("Users", back_populates="gear_components")
    # Define a relationship to the Gear model
    gear = relationship("Gear", back_populates="gear_components")
