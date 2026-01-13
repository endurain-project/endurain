"""User identity provider database models."""

from datetime import datetime
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from core.database import Base


class UserIdentityProvider(Base):
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
        user: Relationship to User model.
        identity_providers: Relationship to IdentityProvider model.
    """

    __tablename__ = "users_identity_providers"

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
        nullable=False,
        server_default=func.now(),
        comment="When this IdP was linked to the user",
    )
    last_login: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Last login using this IdP",
    )
    idp_refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted refresh token",
    )
    idp_access_token_expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Access token expiry time",
    )
    idp_refresh_token_updated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Last refresh token update",
    )

    # Relationships
    # TODO: Change to Mapped["User"] when all modules use mapped
    user = relationship("User", back_populates="user_identity_providers")
    # TODO: Change to Mapped["IdentityProvider"] when all modules use mapped
    identity_providers = relationship(
        "IdentityProvider",
        back_populates="user_identity_providers",
    )
