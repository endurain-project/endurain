from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the gear belongs to",
    )
    message = Column(String, nullable=False, comment="Notification message")
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

    # Define a relationship to the User model
    user = relationship("User", back_populates="notifications")
