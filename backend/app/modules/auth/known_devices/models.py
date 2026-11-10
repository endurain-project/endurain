"""Known-device database models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class KnownDevice(Base):
    """A browser a user has signed in from.

    Attributes:
        id: Primary key.
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id the browser holds in its cookie.
        created_at: When the user first signed in from the device.
        last_seen_at: When the user last signed in from the device.
        security_generation: The account's security generation when the device was last registered; the device is
            known only while it equals the account's current generation.
        browser: Browser the device last signed in with, or None for a device registered before it was recorded.
        operating_system: Operating system the device last signed in with, or None as above.
        device_type: Type of device (Mobile, Tablet, PC) the device last signed in as, or None as above.
    """

    __tablename__ = "auth_known_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_hash", name="uq_auth_known_devices_user_id_device_hash"),)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who signed in from the device",
    )
    device_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hex digest of the device id held in the browser's cookie",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="First sign-in from the device",
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Last sign-in from the device; the row is pruned 400 days after it",
    )
    security_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Account security generation the device was registered under; stale once a security change follows",
    )
    browser: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Browser of the last sign-in from the device",
    )
    operating_system: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Operating system of the last sign-in from the device",
    )
    device_type: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Device type of the last sign-in from the device",
    )
