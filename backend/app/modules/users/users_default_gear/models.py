"""User default gear database models."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class UsersDefaultGear(Base):
    """
    User default gear assignments for activity types.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        run_gear_id: Default gear for run activities.
        trail_run_gear_id: Default gear for trail run activities.
        virtual_run_gear_id: Default gear for virtual run
            activities.
        ride_gear_id: Default gear for ride activities.
        gravel_ride_gear_id: Default gear for gravel ride
            activities.
        mtb_ride_gear_id: Default gear for MTB ride activities.
        virtual_ride_gear_id: Default gear for virtual ride
            activities.
        ows_gear_id: Default gear for open water swim activities.
        walk_gear_id: Default gear for walk activities.
        hike_gear_id: Default gear for hike activities.
        tennis_gear_id: Default gear for tennis activities.
        alpine_ski_gear_id: Default gear for alpine ski
            activities.
        nordic_ski_gear_id: Default gear for nordic ski
            activities.
        snowboard_gear_id: Default gear for snowboard activities.
        windsurf_gear_id: Default gear for windsurf activities.
        user: Relationship to Users model.
    """

    __tablename__ = "users_default_gear"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the default gear belongs",
    )
    run_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default run activity type belongs"),
    )
    trail_run_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default trail run activity type belongs"),
    )
    virtual_run_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default virtual run activity type belongs"),
    )
    ride_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default ride activity type belongs"),
    )
    gravel_ride_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default gravel ride activity type belongs"),
    )
    mtb_ride_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default MTB ride activity type belongs"),
    )
    virtual_ride_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default virtual ride activity type belongs"),
    )
    ows_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default OWS activity type belongs"),
    )
    walk_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default walk activity type belongs"),
    )
    hike_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default hike activity type belongs"),
    )
    tennis_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default tennis activity type belongs"),
    )
    alpine_ski_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default alpine ski activity type belongs"),
    )
    nordic_ski_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default nordic ski activity type belongs"),
    )
    snowboard_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default snowboard activity type belongs"),
    )
    windsurf_gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=("Gear ID that the default windsurf activity type belongs"),
    )

    # Relationships
    users: Mapped["Users"] = relationship(back_populates="users_default_gear")
