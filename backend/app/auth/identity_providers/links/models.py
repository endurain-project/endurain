"""Auth-owned user-to-identity-provider link database models (table: ``users_identity_providers``)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from auth.identity_providers.models import IdentityProvider


class IdentityLink(Base):
    """
    User-to-identity-provider association for SSO/OAuth linking.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        idp_id: Foreign key to identity_providers table.
        idp_subject: Subject/ID from the identity provider.
        linked_at: Timestamp when the IdP was linked.
        last_login: Last login timestamp using this IdP.
        idp_refresh_token: Encrypted refresh token.
        idp_access_token_expires_at: Access token expiry time.
        idp_refresh_token_updated_at: Refresh token update time.
        identity_providers: Relationship to IdentityProvider model.
    """

    __tablename__ = "users_identity_providers"
    __table_args__ = (
        UniqueConstraint("user_id", "idp_id", name="uq_identity_links_user_idp"),
        UniqueConstraint("idp_id", "idp_subject", name="uq_identity_links_idp_subject"),
    )
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID",
    )
    idp_id: Mapped[int] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity Provider ID",
    )
    idp_subject: Mapped[str] = mapped_column(
        String(length=500),
        nullable=False,
        comment="Subject/ID from the identity provider",
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this IdP was linked to the user",
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last login using this IdP",
    )
    idp_refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted refresh token",
    )
    idp_access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Access token expiry time",
    )
    idp_refresh_token_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last refresh token update",
    )

    # Relationships
    identity_providers: Mapped["IdentityProvider"] = relationship(
        back_populates="user_identity_providers",
    )
