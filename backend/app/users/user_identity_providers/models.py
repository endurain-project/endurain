from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base


class UserIdentityProvider(Base):
    """
    Represents the association between a user and an external identity provider.

    Attributes:
        id (int): Primary key.
        user_id (int): Foreign key referencing the associated user.
        idp_id (int): Foreign key referencing the associated identity provider.
        idp_subject (str): Unique subject/identifier from the identity provider for the user.
        linked_at (datetime): Timestamp when the identity provider was linked to the user.
        last_login (datetime, optional): Timestamp of the last login using this identity provider.

    Relationships:
        user (User): The user associated with this identity provider link.
        identity_providers (IdentityProvider): The identity provider associated with this link.
    """

    __tablename__ = "users_identity_providers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID",
    )
    idp_id = Column(
        Integer,
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity Provider ID",
    )
    idp_subject = Column(
        String(length=500),
        nullable=False,
        comment="Subject/ID from the identity provider (unique per IdP)",
    )
    linked_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="When this IdP was linked to the user",
    )
    last_login = Column(
        DateTime, nullable=True, comment="Last time user logged in with this IdP"
    )
    idp_refresh_token = Column(Text, nullable=True, comment="Encrypted refresh token")
    idp_access_token_expires_at = Column(
        DateTime, nullable=True, comment="Access token expiry time"
    )
    idp_refresh_token_updated_at = Column(
        DateTime, nullable=True, comment="Last refresh"
    )

    # Relationships
    user = relationship("User", back_populates="user_identity_providers")
    identity_providers = relationship(
        "IdentityProvider", back_populates="user_identity_providers"
    )
