from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class ComputerModel(Base):
    """Lookup table for known watch/computer models (Garmin, Suunto, etc.)"""

    __tablename__ = "computer_models"

    id = Column(Integer, primary_key=True)
    manufacturer = Column(
        String(length=50),
        nullable=False,
        index=True,
        comment="Manufacturer (garmin, suunto, etc.)",
    )
    product_code = Column(
        String(length=100),
        nullable=True,
        index=True,
        comment="Product code from FIT file (e.g., fenix7x, edge530)",
    )
    product_id = Column(
        Integer,
        nullable=True,
        index=True,
        comment="Numeric product ID from FIT file",
    )
    model_name = Column(
        String(length=200),
        nullable=False,
        comment="Human-readable model name (e.g., Fenix 7X, Edge 530)",
    )
    region = Column(
        String(length=50),
        nullable=True,
        comment="Region variant (Asia, Japan, etc.)",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Record creation timestamp",
    )

    # Relationship to gear items using this computer model
    gear = relationship("Gear", back_populates="computer_model")
