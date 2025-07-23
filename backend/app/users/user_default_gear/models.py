from sqlalchemy import Column, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class UsersDefaultGear(Base):
    __tablename__ = "users_default_gear"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the default gear belongs",
    )
    run_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default run activity type belongs",
    )
    trail_run_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default trail run activity type belongs",
    )
    virtual_run_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default virtual run activity type belongs",
    )
    ride_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default ride activity type belongs",
    )
    gravel_ride_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default gravel ride activity type belongs",
    )
    mtb_ride_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default MTB ride activity type belongs",
    )
    virtual_ride_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default virtual ride activity type belongs",
    )
    ows_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default OWS activity type belongs",
    )
    walk_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default walk activity type belongs",
    )
    hike_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default hike activity type belongs",
    )
    tennis_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default tennis activity type belongs",
    )
    alpine_ski_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default alpine ski activity type belongs",
    )
    nordic_ski_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default nordic ski activity type belongs",
    )
    snowboard_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default snowboard activity type belongs",
    )
    windsurf_gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID that the default windsurf activity type belongs",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="users_default_gear")

    # Define a relationship to the Gear model
    run_gear = relationship("Gear", foreign_keys=[run_gear_id])
    trail_run_gear = relationship("Gear", foreign_keys=[trail_run_gear_id])
    virtual_run_gear = relationship("Gear", foreign_keys=[virtual_run_gear_id])
    ride_gear = relationship("Gear", foreign_keys=[ride_gear_id])
    gravel_ride_gear = relationship("Gear", foreign_keys=[gravel_ride_gear_id])
    mtb_ride_gear = relationship("Gear", foreign_keys=[mtb_ride_gear_id])
    virtual_ride_gear = relationship("Gear", foreign_keys=[virtual_ride_gear_id])
    ows_gear = relationship("Gear", foreign_keys=[ows_gear_id])
    walk_gear = relationship("Gear", foreign_keys=[walk_gear_id])
    hike_gear = relationship("Gear", foreign_keys=[hike_gear_id])
    tennis_gear = relationship("Gear", foreign_keys=[tennis_gear_id])
    alpine_ski_gear = relationship("Gear", foreign_keys=[alpine_ski_gear_id])
    nordic_ski_gear = relationship("Gear", foreign_keys=[nordic_ski_gear_id])
    snowboard_gear = relationship("Gear", foreign_keys=[snowboard_gear_id])
    windsurf_gear = relationship("Gear", foreign_keys=[windsurf_gear_id])
