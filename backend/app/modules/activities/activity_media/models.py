"""SQLAlchemy ORM models for activity media records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


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

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the media record was created",
    )
