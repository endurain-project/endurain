from sqlalchemy import (
    Column,
    Integer,
    String,
    DATETIME,
    ForeignKey,
    Boolean,
    DECIMAL,
    Enum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

import gears.gear_components.schema as gear_components_schema

from core.database import Base


# Data model for gear table using SQLAlchemy's ORM
class GearComponents(Base):
    __tablename__ = "gear_components"

    id = Column(Integer, primary_key=True)
    gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID associated with this component",
    )
    type = Column(
        Enum(gear_components_schema.GearComponentType),
        nullable=False,
        comment="Type of gear component (enum)",
    )
    brand = Column(
        String(length=250),
        nullable=True,
        comment="Gear component brand (May include spaces)",
    )
    model = Column(
        String(length=250),
        nullable=True,
        comment="Gear component model (May include spaces)",
    )
    purchase_date = Column(
        DATETIME,
        nullable=False,
        default=func.now(),
        comment="Gear component purchase date (DATETIME)",
    )
    retired_date = Column(
        DATETIME,
        nullable=True,
        comment="Gear component retired date (DATETIME)",
    )
    is_active = Column(
        Boolean, nullable=False, default=False, comment="Is gear component active"
    )
    expected_kms = Column(
        DECIMAL(precision=11, scale=3),
        nullable=False,
        default=0,
        comment="Expected kilometers of the gear component",
    )
    purchase_value = Column(
        DECIMAL(precision=11, scale=3),
        nullable=False,
        default=0,
        comment="Purchase value of the gear component",
    )

    gear = relationship("Gear", back_populates="gear_components")
