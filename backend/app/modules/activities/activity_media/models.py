"""SQLAlchemy ORM models for activity media records."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.activities.activity.models import Activity


class ActivityMedia(Base):
    """Photo or video media attached to an activity."""

    __tablename__ = "activity_media"

    __table_args__ = (
        # Read-then-write dedup checks (create_activity_media) race the same way
        # activities.dedup_key does: two concurrent stores of the same photo can
        # both see "not found" and both insert. NULL hashes stay unconstrained
        # (Postgres treats NULLs as distinct), so media with no computed hash is
        # unaffected.
        Index("uq_activity_media_activity_content_hash", "activity_id", "content_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity media belongs",
    )
    media_path: Mapped[str | None] = mapped_column(
        String(length=250),
        unique=True,
        comment="Media path",
    )
    media_type: Mapped[int] = mapped_column(
        nullable=False,
        comment="Media type (1 - photo)",
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(length=64),
        comment="SHA-256 of the media bytes, used to no-op re-imports of the same photo",
    )

    # Define a relationship to the Activity model
    activity: Mapped["Activity"] = relationship(back_populates="activity_media")
