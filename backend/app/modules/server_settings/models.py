"""ORM model for the singleton server settings row."""

from sqlalchemy import CheckConstraint, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column

import modules.server_settings.constants as server_settings_constants
from core.database import Base


class ServerSettings(Base):
    """Server-wide configuration settings.

    Attributes:
        id: Primary key (always 1, singleton pattern).
        units: Measurement units (metric, imperial).
        public_shareable_links: Allow public shareable links.
        public_shareable_links_user_info: Show user info on
            public links.
        login_photo_set: Login photo has been configured.
        currency: Currency type (euro, dollar, pound).
        num_records_per_page: Default pagination size.
        signup_enabled: Allow user registration.
        signup_require_admin_approval: Require approval for
            new signups.
        signup_require_email_verification: Require email
            verification for new signups.
        sso_enabled: Enable SSO/IdP login.
        local_login_enabled: Allow local login.
        sso_auto_redirect: Auto-redirect to SSO.
        tileserver_url: Map tile server URL template.
        tileserver_attribution: Map tile attribution.
        tileserver_api_key: API key for tile server (encrypted).
        tileserver_regenerate_thumbnails_on_change: Regenerate
            thumbnails when tile server settings change.
        map_background_color: Map background hex color.
        password_type: Password policy type.
        password_length_regular_users: Min password length
            for regular users.
        password_length_admin_users: Min password length for
            admin users.
        geocoding_service: Reverse-geocoding service.
        geocoding_host: Geocoding service host (NULL - default host).
        geocoding_use_https: Address the geocoding host over HTTPS.
        geocoding_rate_limit: Geocoding requests per second.
        geocoding_api_key: API key for the geocoding service (encrypted).
        session_idle_timeout_enabled: Enforce session idle and absolute timeouts.
        session_idle_timeout_hours: Hours of inactivity that end a session.
        session_absolute_timeout_hours: Hours after which a session ends.
        access_token_expire_minutes: Access token lifetime in minutes.
        refresh_token_expire_days: Refresh token lifetime in days.
        read_notification_retention_days: Days after which read notifications are purged (0 - never).
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    __tablename__ = "server_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        default=1,
        nullable=False,
    )
    units: Mapped[str] = mapped_column(
        String(20),
        default="metric",
        nullable=False,
        comment="Units (metric, imperial)",
    )
    public_shareable_links: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Allow public shareable links (true - yes, false - no)",
    )
    public_shareable_links_user_info: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Allow show user info on public shareable links (true - yes, false - no)",
    )
    login_photo_set: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Is login photo set (true - yes, false - no)",
    )
    currency: Mapped[str] = mapped_column(
        String(20),
        default="euro",
        nullable=False,
        comment="Currency (euro, dollar, pound)",
    )
    num_records_per_page: Mapped[int] = mapped_column(
        default=25,
        nullable=False,
        comment="Number of records per page in lists",
    )
    signup_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Allow user sign-up registration (true - yes, false - no)",
    )
    signup_require_admin_approval: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Require admin approval for new sign-ups (true - yes, false - no)",
    )
    signup_require_email_verification: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Require email verification for new sign-ups (true - yes, false - no)",
    )
    sso_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Enable SSO/IdP login (true - yes, false - no)",
    )
    local_login_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Allow local username/password login (true - yes, false - no)",
    )
    sso_auto_redirect: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Auto-redirect to SSO if only one IdP (true - yes, false - no)",
    )
    tileserver_url: Mapped[str] = mapped_column(
        default=server_settings_constants.DEFAULT_TILE_URL,
        nullable=False,
        comment="URL template for the map tileserver",
    )
    tileserver_attribution: Mapped[str] = mapped_column(
        default=server_settings_constants.DEFAULT_TILE_ATTRIBUTION,
        nullable=False,
        comment="Attribution string for the map tileserver",
    )
    tileserver_api_key: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=("API key encrypted for the tile server"),
    )
    tileserver_regenerate_thumbnails_on_change: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Delete and regenerate all activity thumbnails when tile server settings change"),
    )
    map_background_color: Mapped[str] = mapped_column(
        default="#dddddd",
        nullable=False,
        comment="Background color for the map (hex format)",
    )
    password_type: Mapped[str] = mapped_column(
        default="strict",
        nullable=False,
        comment="Password type policy (strict, length_only)",
    )
    password_length_regular_users: Mapped[int] = mapped_column(
        default=8,
        nullable=False,
        comment="Minimum password length for regular users",
    )
    password_length_admin_users: Mapped[int] = mapped_column(
        default=12,
        nullable=False,
        comment="Minimum password length for admin users",
    )

    geocoding_service: Mapped[str] = mapped_column(
        String(20),
        default="nominatim",
        server_default="nominatim",
        nullable=False,
        comment="Reverse-geocoding service (nominatim, photon, geocode)",
    )
    geocoding_host: Mapped[str | None] = mapped_column(
        String(253),
        default=None,
        nullable=True,
        comment="Host of the geocoding service (NULL - the service's default host)",
    )
    geocoding_use_https: Mapped[bool] = mapped_column(
        default=True,
        server_default=text("true"),
        nullable=False,
        comment="Address the geocoding host over HTTPS (true - yes, false - no)",
    )
    geocoding_rate_limit: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        server_default=text("1.0"),
        nullable=False,
        comment="Maximum geocoding requests per second (0 disables throttling)",
    )
    geocoding_api_key: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment="API key encrypted for the geocoding service",
    )

    session_idle_timeout_enabled: Mapped[bool] = mapped_column(
        default=False,
        server_default=text("false"),
        nullable=False,
        comment="Enforce session idle and absolute timeouts (true - yes, false - no)",
    )
    session_idle_timeout_hours: Mapped[int] = mapped_column(
        default=1,
        server_default=text("1"),
        nullable=False,
        comment="Hours of inactivity after which a session ends",
    )
    session_absolute_timeout_hours: Mapped[int] = mapped_column(
        default=24,
        server_default=text("24"),
        nullable=False,
        comment="Hours after which a session ends whatever its activity",
    )
    access_token_expire_minutes: Mapped[int] = mapped_column(
        default=15,
        server_default=text("15"),
        nullable=False,
        comment="Access token lifetime in minutes",
    )
    refresh_token_expire_days: Mapped[int] = mapped_column(
        default=7,
        server_default=text("7"),
        nullable=False,
        comment="Refresh token lifetime in days",
    )

    read_notification_retention_days: Mapped[int] = mapped_column(
        default=90,
        server_default=text("90"),
        nullable=False,
        comment="Days after which read notifications are purged (0 - never)",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    __table_args__ = (
        CheckConstraint("id = 1", name="single_row_check"),
        CheckConstraint(
            "read_notification_retention_days BETWEEN 0 AND 3650", name="read_notification_retention_days_check"
        ),
        CheckConstraint("session_idle_timeout_hours BETWEEN 1 AND 8760", name="session_idle_timeout_hours_check"),
        CheckConstraint(
            "session_absolute_timeout_hours BETWEEN 1 AND 8760", name="session_absolute_timeout_hours_check"
        ),
        CheckConstraint("access_token_expire_minutes BETWEEN 1 AND 1440", name="access_token_expire_minutes_check"),
        CheckConstraint("refresh_token_expire_days BETWEEN 1 AND 365", name="refresh_token_expire_days_check"),
        CheckConstraint(
            "session_absolute_timeout_hours >= session_idle_timeout_hours", name="session_absolute_not_below_idle_check"
        ),
        CheckConstraint("geocoding_rate_limit BETWEEN 0 AND 100", name="geocoding_rate_limit_check"),
        CheckConstraint("geocoding_service IN ('nominatim', 'photon', 'geocode')", name="geocoding_service_check"),
    )


class MailSettings(Base):
    """Outgoing mail server configuration.

    Attributes:
        id: Primary key (always 1, singleton pattern).
        host: Mail server hostname; NULL means mail is disabled.
        port: Mail server port.
        security: Connection security (starttls, ssl, none).
        username: Authentication username.
        password: Authentication password (encrypted).
        from_address: Sender address; the username is used when NULL.
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    __tablename__ = "mail_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        default=1,
        nullable=False,
    )
    host: Mapped[str | None] = mapped_column(
        String(253),
        default=None,
        nullable=True,
        comment="Mail server hostname (NULL - mail disabled)",
    )
    port: Mapped[int] = mapped_column(
        default=587,
        server_default=text("587"),
        nullable=False,
        comment="Mail server port",
    )
    security: Mapped[str] = mapped_column(
        String(10),
        default="starttls",
        server_default="starttls",
        nullable=False,
        comment="Connection security (starttls, ssl, none)",
    )
    username: Mapped[str | None] = mapped_column(
        String(320),
        default=None,
        nullable=True,
        comment="Mail server authentication username",
    )
    password: Mapped[str | None] = mapped_column(
        String(512),
        default=None,
        nullable=True,
        comment="Mail server authentication password (encrypted)",
    )
    from_address: Mapped[str | None] = mapped_column(
        String(320),
        default=None,
        nullable=True,
        comment="Sender address (NULL - the username is used)",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    __table_args__ = (
        CheckConstraint("id = 1", name="mail_settings_single_row_check"),
        CheckConstraint("security IN ('starttls', 'ssl', 'none')", name="mail_settings_security_check"),
    )
