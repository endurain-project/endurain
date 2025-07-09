from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON
from core.database import Base

# Data model for activities table using SQLAlchemy's ORM
class Segment(Base):
    __tablename__ = "segments"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="ID for the segment"
        )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the Segment belongs to"
        )

    name = Column(
        String(length=250),
        nullable=True,
        comment="Segment name (May include spaces)"
        )

    activity_type = Column(
        Integer,
        nullable=False,
        comment="Activity type")

    splits = Column(
        JSON,
        nullable=False,
        doc="Store gates data"
        )