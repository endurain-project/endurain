from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the gear belongs to",
    )
    type = Column(
        Integer,
        nullable=False,
        comment="Notification type",
    )
    options = Column(
        JSON,
        nullable=True,
        comment="Notification options (JSON)",
    )
    read = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Has the notification been read (True) or not (False)",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Notification creation date (DateTime)",
    )

    # Define a relationship to the Users model
    users = relationship("Users", back_populates="notifications")
