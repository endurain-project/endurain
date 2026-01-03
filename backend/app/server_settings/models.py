from sqlalchemy import Column, Integer, Boolean, CheckConstraint, String
from core.database import Base


class ServerSettings(Base):
    __tablename__ = "server_settings"

    id = Column(Integer, primary_key=True, default=1, nullable=False)
    units = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Units (one digit)(1 - metric, 2 - imperial)",
    )
    public_shareable_links = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow public shareable links (true - yes, false - no)",
    )
    public_shareable_links_user_info = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow show user info on public shareable links (true - yes, false - no)",
    )
    login_photo_set = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Is login photo set (true - yes, false - no)",
    )
    currency = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Currency (one digit)(1 - euro, 2 - dollar, 3 - pound)",
    )
    num_records_per_page = Column(
        Integer,
        nullable=False,
        default=25,
        comment="Number of records per page in lists",
    )
    signup_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow user sign-up registration (true - yes, false - no)",
    )
    signup_require_admin_approval = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Require admin approval for new sign-ups (true - yes, false - no)",
    )
    signup_require_email_verification = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Require email verification for new sign-ups (true - yes, false - no)",
    )
    sso_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Enable SSO/IdP login (true - yes, false - no)",
    )
    local_login_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Allow local username/password login (true - yes, false - no)",
    )
    sso_auto_redirect = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Auto-redirect to SSO if only one IdP (true - yes, false - no)",
    )
    tileserver_url = Column(
        String,
        nullable=False,
        default="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        comment="URL template for the map tileserver",
    )
    tileserver_attribution = Column(
        String,
        nullable=False,
        default='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        comment="Attribution string for the map tileserver",
    )
    map_background_color = Column(
        String,
        nullable=False,
        default="#dddddd",
        comment="Background color for the map",
    )

    __table_args__ = (CheckConstraint("id = 1", name="single_row_check"),)
