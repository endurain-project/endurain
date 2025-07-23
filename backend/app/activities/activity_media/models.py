from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DECIMAL,
    DateTime,
)
from sqlalchemy.orm import relationship
from core.database import Base


class ActivityMedia(Base):
    __tablename__ = "activity_media"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity media belongs",
    )
    media_path = Column(
        String(length=250), nullable=True, unique=True, comment="Media path"
    )
    media_type = Column(
        Integer,
        nullable=False,
        comment="Media type (1 - photo)",
    )

    # Define a relationship to the Activity model
    activity = relationship("Activity", back_populates="activity_media")
