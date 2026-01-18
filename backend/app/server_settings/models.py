from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class ServerSettings(Base):
    """
    Server-wide configuration settings.

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
        map_background_color: Map background hex color.
        password_type: Password policy type.
        password_length_regular_users: Min password length
            for regular users.
        password_length_admin_users: Min password length for
            admin users.
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
        default=("https://{s}.tile.openstreetmap.org/" "{z}/{x}/{y}.png"),
        nullable=False,
        comment="URL template for the map tileserver",
    )
    tileserver_attribution: Mapped[str] = mapped_column(
        default=(
            '&copy; <a href="https://www.openstreetmap.org/'
            'copyright">OpenStreetMap</a> contributors'
        ),
        nullable=False,
        comment="Attribution string for the map tileserver",
    )
    tileserver_api_key: Mapped[str | None] = mapped_column(
        String(length=512),
        default=None,
        nullable=True,
        comment=("API key encrypted for the tile server"),
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

    __table_args__ = (CheckConstraint("id = 1", name="single_row_check"),)
