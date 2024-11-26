from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
)
from core.database import Base


class Migration(Base):
    __tablename__ = "migrations"

    id = Column(Integer, primary_key=True)
    name = Column(String(length=250), nullable=False, comment="Migration name")
    description = Column(
        String(length=2500), nullable=False, comment="Migration description"
    )
    executed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the migration was executed or not",
    )