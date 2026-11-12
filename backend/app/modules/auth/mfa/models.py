"""SQLAlchemy ORM model for the ``mfa_factors`` table.

A user's enrolled second factors, one row each. A user has MFA while at least one row exists. Rows are written by
``modules.auth.mfa.crud``; the earlier ``users_mfa`` table is no longer read or written.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

import modules.auth.constants as auth_constants
from core.database import Base

#: The values ``type`` may hold: one per ``MFAFactorType``.
_FACTOR_TYPE_VALUES = ", ".join(f"'{factor_type.value}'" for factor_type in auth_constants.MFAFactorType)
_TOTP_ONLY = text(f"type = '{auth_constants.MFAFactorType.TOTP.value}'")


class MFAFactor(Base):
    """An enrolled second factor.

    Attributes:
        id: Primary key, a random UUID.
        user_id: FK to ``users.id``.
        type: The kind of factor (``MFAFactorType``).
        credential: The factor's secret, Fernet-encrypted: the TOTP secret.
        created_at: When the factor was enrolled.
        last_used_at: When the factor last verified a sign-in or step-up, or ``None`` if it has not.
    """

    __tablename__ = "mfa_factors"
    __table_args__ = (
        CheckConstraint(f"type IN ({_FACTOR_TYPE_VALUES})", name="ck_mfa_factors_type"),
        Index(
            "uq_mfa_factors_user_totp",
            "user_id",
            unique=True,
            postgresql_where=_TOTP_ONLY,
            sqlite_where=_TOTP_ONLY,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK to users",
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False, comment="Factor type: totp")
    credential: Mapped[str] = mapped_column(String(512), nullable=False, comment="Fernet-encrypted factor secret")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When the factor was enrolled",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the factor last verified a sign-in or step-up",
    )
