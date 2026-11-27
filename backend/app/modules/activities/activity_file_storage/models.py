"""SQLAlchemy ORM model for retained activity source files."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ActivityFile(Base):
    """One retained original activity file and where its blob is stored.

    Attributes:
        id: Primary key, a random UUID that names the blob.
        user_id: Owner of the file.
        sha256: Hex SHA-256 of the file's bytes.
        storage_key: The blob's key in the activity-files storage area.
        extension: The file's extension with its dot, such as ``.fit``.
        size_bytes: The file's size.
        state: ``pending``, ``attached`` or ``deleting``.
        created_at: When the row was created.
        updated_at: When the row last changed state or was taken again by an upload; the sweep ages rows by it.
    """

    __tablename__ = "activity_files"

    __table_args__ = (
        # One live row per user and content: an upload of bytes the user already retained shares the row. A row
        # being deleted is outside the index, so a re-upload during the deletion stages a new row and a new key
        # instead of waiting for, or reviving, a blob a job is about to delete.
        Index(
            "uq_activity_files_user_sha256_live",
            "user_id",
            "sha256",
            unique=True,
            postgresql_where=text("state <> 'deleting'"),
        ),
        # The daily sweep reads the rows that are not attached.
        Index(
            "ix_activity_files_state_updated_at", "state", "updated_at", postgresql_where=text("state <> 'attached'")
        ),
        CheckConstraint("state IN ('pending', 'attached', 'deleting')", name="ck_activity_files_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT: a cascade would drop rows whose blobs still exist, so account erasure removes them first.
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="User ID that owns the retained file",
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, comment="Hex SHA-256 of the file's bytes")
    storage_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Key of the file's blob in the activity-files storage area",
    )
    extension: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="File extension with its dot (.gpx, .fit or .tcx)"
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Size of the file in bytes")
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="pending (blob being written), attached (an activity references it) or deleting (blob being removed)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="When the row was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the row last changed state or was taken again by an upload",
    )
