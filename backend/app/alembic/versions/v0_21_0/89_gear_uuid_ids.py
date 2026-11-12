"""89: gear and gear components get UUID ids

``gear.id``, ``gear_components.id`` and the 17 columns that hold a gear id become random ``uuid`` values: the gear
column of ``activities`` and ``gear_components`` and the 15 columns of ``users_default_gear``. Their foreign keys (with
the same ``ON DELETE``), indexes and comments are recreated under the same names.

``gear_components`` gets ``created_at``, filled in the old id order, so the order of the components survives.

Both gear tombstone tables are emptied: their ``record_id`` names rows whose ids change, and a cursor from before the
upgrade answers 410.

No stored payload, event metadata, notification option or stored-file key holds these ids, so nothing is rewritten and
data migration 13 is not scheduled. The provider gear ids (``strava_gear_id``, ``garminconnect_gear_id``) are
untouched.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: ecaa46b32646
Revises: dc5f0450aaf0
Create Date: 2026-11-12 12:00:00.000000

"""

from collections.abc import Sequence

from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex, IdReference

# revision identifiers, used by Alembic.
revision: str = "ecaa46b32646"
down_revision: str | None = "dc5f0450aaf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARENT = "gear"

_PARENT_INDEXES = (IdIndex("ix_gear_user_id_updated_at_id", ("user_id", "updated_at", "id")),)

_COMPONENT_INDEXES = (IdIndex("ix_gear_components_user_id_updated_at_id", ("user_id", "updated_at", "id")),)

_REFERENCES: tuple[IdReference, ...] = (
    IdReference(
        "activities",
        "gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID associated with this activity",
        indexes=(IdIndex("ix_activities_gear_id", ("gear_id",)),),
    ),
    IdReference(
        "gear_components",
        "gear_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Gear ID associated with this component",
        indexes=(IdIndex("ix_gear_components_gear_id", ("gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "run_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default run activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_run_gear_id", ("run_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "trail_run_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default trail run activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_trail_run_gear_id", ("trail_run_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "virtual_run_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default virtual run activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_virtual_run_gear_id", ("virtual_run_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "ride_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default ride activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_ride_gear_id", ("ride_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "gravel_ride_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default gravel ride activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_gravel_ride_gear_id", ("gravel_ride_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "mtb_ride_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default MTB ride activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_mtb_ride_gear_id", ("mtb_ride_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "virtual_ride_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default virtual ride activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_virtual_ride_gear_id", ("virtual_ride_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "ows_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default OWS activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_ows_gear_id", ("ows_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "walk_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default walk activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_walk_gear_id", ("walk_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "hike_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default hike activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_hike_gear_id", ("hike_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "tennis_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default tennis activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_tennis_gear_id", ("tennis_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "alpine_ski_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default alpine ski activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_alpine_ski_gear_id", ("alpine_ski_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "nordic_ski_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default nordic ski activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_nordic_ski_gear_id", ("nordic_ski_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "snowboard_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default snowboard activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_snowboard_gear_id", ("snowboard_gear_id",)),),
    ),
    IdReference(
        "users_default_gear",
        "windsurf_gear_id",
        nullable=True,
        ondelete="SET NULL",
        comment="Gear ID that the default windsurf activity type belongs",
        indexes=(IdIndex("ix_users_default_gear_windsurf_gear_id", ("windsurf_gear_id",)),),
    ),
)


def upgrade() -> None:
    """Order the components, empty the tombstones and swap the gear ids for UUIDs."""
    uuid_conversion.add_created_at_in_id_order("gear_components", comment="When the component was created")
    uuid_conversion.empty_tombstones("gear_deletions")
    uuid_conversion.empty_tombstones("gear_component_deletions")
    uuid_conversion.add_uuid_ids_with_references(_PARENT, _REFERENCES)
    uuid_conversion.swap_in_uuid_ids(_PARENT, _PARENT_INDEXES, _REFERENCES)
    uuid_conversion.give_uuid_primary_key("gear_components", _COMPONENT_INDEXES)


def downgrade() -> None:
    """Refuse: the integer ids are gone.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError(
        "Revision 89 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
