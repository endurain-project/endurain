"""User integrations database models."""

from datetime import datetime
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class UsersIntegrations(Base):
    """
    User third-party service integration settings.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table (unique).
        strava_client_id: Encrypted Strava client ID.
        strava_client_secret: Encrypted Strava client secret.
        strava_state: Temporary state for Strava OAuth flow.
        strava_token: Encrypted Strava access token.
        strava_refresh_token: Encrypted Strava refresh token.
        strava_token_expires_at: Strava token expiration
            timestamp.
        strava_sync_gear: Enable Strava gear synchronization.
        garminconnect_oauth1: Garmin Connect OAuth1 token
            data.
        garminconnect_oauth2: Garmin Connect OAuth2 token
            data.
        garminconnect_sync_gear: Enable Garmin Connect gear
            synchronization.
        user: Relationship to User model.
    """

    __tablename__ = "users_integrations"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the integration belongs",
    )
    strava_client_id: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=("Strava client ID encrypted at rest with Fernet key"),
    )
    strava_client_secret: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=("Strava client secret encrypted at rest with Fernet key"),
    )
    strava_state: Mapped[str | None] = mapped_column(
        String(length=45),
        default=None,
        nullable=True,
        comment="Strava temporary state for link process",
    )
    strava_token: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=("Strava token after link process encrypted at rest with Fernet key"),
    )
    strava_refresh_token: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=(
            "Strava refresh token after link process encrypted at rest with Fernet key"
        ),
    )
    strava_token_expires_at: Mapped[datetime | None] = mapped_column(
        default=None,
        nullable=True,
        comment="Strava token expiration date",
    )
    strava_sync_gear: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether Strava gear is to be synced",
    )
    garminconnect_oauth1: Mapped[dict | None] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        comment="Garmin OAuth1 token",
    )
    garminconnect_oauth2: Mapped[dict | None] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        comment="Garmin OAuth2 token",
    )
    garminconnect_sync_gear: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether Garmin Connect gear is to be synced",
    )

    # Define a relationship to the User model
    # TODO: Change to Mapped["User"] when all modules use mapped
    user = relationship("User", back_populates="users_integrations")
