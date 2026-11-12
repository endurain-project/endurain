"""Auth-owned identity-provider link and sign-in database models (tables: ``users_identity_providers``, ``idp_session_tokens``)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class IdentityLink(Base):
    """User-to-identity-provider association for SSO/OAuth linking.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Foreign key to users table.
        idp_id: Foreign key to identity_providers table.
        idp_subject: Subject/ID from the identity provider.
        linked_at: Timestamp when the IdP was linked.
        last_login: Last login timestamp using this IdP.
    """

    __tablename__ = "users_identity_providers"
    __table_args__ = (
        UniqueConstraint("user_id", "idp_id", name="uq_identity_links_user_idp"),
        UniqueConstraint("idp_id", "idp_subject", name="uq_identity_links_idp_subject"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID",
    )
    idp_id: Mapped[uuid.UUID] = mapped_column(
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


class IdpSessionToken(Base):
    """The identity-provider sign-in behind one Endurain session, with the refresh token it was issued.

    There is no foreign key to the sessions table: the row outlives the session long enough for its token to be
    revoked at the provider.

    Attributes:
        id: Primary key, a random UUID.
        session_id: The Endurain session the user signed in with.
        user_id: Foreign key to users table.
        idp_id: Foreign key to identity_providers table.
        refresh_token: Encrypted refresh token; ``None`` when the provider issued none.
        id_token: Encrypted ID token the provider issued at sign-in, kept to name the session at RP-initiated
            logout; ``None`` when the provider issued none.
        idp_sid: The provider's session id (``sid``) from the verified ID token, which a back-channel logout token
            names; ``None`` when the ID token carried none.
        access_token_expires_at: Access token expiry time.
        refresh_token_updated_at: When the refresh token was last stored.
        created_at: When the session signed in.
    """

    __tablename__ = "idp_session_tokens"
    __table_args__ = (Index("ix_idp_session_tokens_idp_id_idp_sid", "idp_id", "idp_sid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(
        String(length=36),
        nullable=False,
        unique=True,
        comment="Endurain session the sign-in created; no foreign key, so the token outlives the session row",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID",
    )
    idp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity Provider ID",
    )
    refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted refresh token",
    )
    id_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted ID token the provider issued at sign-in",
    )
    idp_sid: Mapped[str | None] = mapped_column(
        String(length=255),
        nullable=True,
        comment="Provider session id (sid) of the verified ID token, named by back-channel logout",
    )
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Access token expiry time",
    )
    refresh_token_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last refresh token update",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the session signed in through the provider",
    )
