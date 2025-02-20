from sqlalchemy import Column, Integer, Boolean, CheckConstraint
from core.database import Base


class ServerSettings(Base):
    __tablename__ = "server_settings"

    id = Column(Integer, primary_key=True, default=1, nullable=False)
    units = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User units (one digit)(1 - metric, 2 - imperial)",
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

    __table_args__ = (CheckConstraint("id = 1", name="single_row_check"),)
