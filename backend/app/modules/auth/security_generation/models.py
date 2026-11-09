"""SQLAlchemy ORM model for the ``account_security_generations`` table.

The row is created lazily, so an account without one is at generation 0. Rows are written and read through
``modules.auth.security_generation.crud``.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class AccountSecurityGeneration(Base):
    """Security generation of an account (1:1 with ``users``).

    Attributes:
        user_id: FK to ``users.id`` and primary key (one row per user).
        generation: Counter advanced by every security change; a pending proof records the value it was
            created under.
        updated_at: When the generation last changed.
    """

    __tablename__ = "account_security_generations"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="User the generation belongs to",
    )
    generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Counter advanced by every security change; a pending proof records the value it was created under",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When the generation last changed",
    )
