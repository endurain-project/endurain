from sqlalchemy import Column, Integer, CheckConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ServerSettings(Base):
    __tablename__ = "server_settings"

    id = Column(Integer, primary_key=True, default=1, nullable=False)
    units = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User units (one digit)(1 - metric, 2 - imperial)",
    )

    __table_args__ = (CheckConstraint("id = 1", name="single_row_check"),)
