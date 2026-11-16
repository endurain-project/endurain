"""COROS integration database models."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class CorosIntegration(Base):
    """One user's COROS OAuth connection and sync bookkeeping.

    Tokens and the short-lived PKCE verifier are stored Fernet-encrypted. The
    client id is public (COROS registers public OAuth clients), and no token is
    ever returned by the API.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the owning user (unique).
        mcp_url: Regional MCP endpoint discovered during authorization.
        issuer: OAuth issuer discovered during authorization.
        redirect_uri: Callback URI registered with COROS.
        scope: Granted OAuth scopes.
        client_id: Dynamically registered public OAuth client id.
        client_secret: Encrypted client secret, when COROS issues one.
        state: Current OAuth state, or None outside a pending authorization.
        code_verifier: Encrypted PKCE verifier for the pending authorization.
        state_expires_at: Expiry of the pending authorization.
        access_token: Encrypted access token.
        refresh_token: Encrypted refresh token.
        token_expires_at: Access-token expiry.
        refresh_token_expires_at: Refresh-token expiry.
        last_sync_at: Last sync attempt time.
        last_sync_status: ``never``, ``success`` or ``error``.
        last_sync_error: Sanitized failure code, or None.
        last_sync_activity_count: Activities stored by the last successful sync.
        fit_download_date: UTC date the FIT download counter belongs to.
        fit_download_count: FIT downloads already spent on that date.
        created_at: Row creation time.
        updated_at: Last update time.
    """

    __tablename__ = "coros_integrations"
    __table_args__ = (
        Index("ix_coros_integrations_user_id", "user_id", unique=True),
        Index("ix_coros_integrations_state", "state", unique=True),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the COROS integration belongs to",
    )
    mcp_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Regional COROS MCP endpoint",
    )
    issuer: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="COROS OAuth issuer",
    )
    redirect_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OAuth callback URI registered with COROS",
    )
    scope: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Granted OAuth scopes",
    )
    client_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Dynamically registered public OAuth client ID",
    )
    client_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="COROS OAuth client secret encrypted at rest with Fernet key",
    )
    state: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Temporary OAuth state for the link process",
    )
    code_verifier: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="PKCE verifier encrypted at rest with Fernet key",
    )
    state_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Expiry of the pending OAuth state",
    )
    access_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="COROS access token encrypted at rest with Fernet key",
    )
    refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="COROS refresh token encrypted at rest with Fernet key",
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="COROS access token expiration date",
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="COROS refresh token expiration date",
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last COROS sync attempt",
    )
    last_sync_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="never",
        comment="Outcome of the most recent COROS sync",
    )
    last_sync_error: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Sanitized reason for the most recent failed COROS sync",
    )
    last_sync_activity_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Activities stored by the most recent successful COROS sync",
    )
    fit_download_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="UTC date the COROS FIT download counter belongs to",
    )
    fit_download_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="COROS FIT downloads already requested on fit_download_date",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Row creation date",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Last row update date",
    )


class CorosSkippedActivity(Base):
    """An activity COROS cannot provide a FIT file for.

    Retrying the download on every sync would burn the shared 50-file daily
    quota on the same activity. The marker makes the skip explicit and cheap.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the owning user.
        label_id: COROS activity identifier.
        reason: Why the activity was skipped (``no_file`` or ``invalid_file``).
        created_at: When the activity was first skipped.
    """

    __tablename__ = "coros_skipped_activities"
    __table_args__ = (UniqueConstraint("user_id", "label_id", name="uq_coros_skipped_activities_user_label"),)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the skipped COROS activity belongs to",
    )
    label_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="COROS activity identifier",
    )
    reason: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Why the COROS activity was skipped",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the activity was first skipped",
    )
