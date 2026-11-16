"""87: UUID primary keys for the tables nothing else references

The ``id`` of 25 tables becomes a random ``uuid``: the seven health tables and the four sync tombstone tables,
``users_goals``, ``notifications``, ``followers``, ``follower_blocks``, ``follow_request_declines``,
``auth_known_devices``, ``mfa_factors``, ``mfa_backup_codes``, ``rotated_refresh_tokens``, ``users_integrations``,
``users_privacy_settings``, ``users_default_gear``, ``users_identity_providers`` and ``idp_session_tokens``.

``users_goals`` gets a ``created_at`` filled in the old id order. ``followers`` and ``follower_blocks`` already have
one, so each of their rows keeps it unless it ties with or precedes the row with the next lower id: it then becomes
that row's value plus one microsecond. Sorting by ``created_at`` keeps the order the integer ids gave.

No stored payload, metadata or JSON document holds these ids, so the revision rewrites none. ``health_record_deletions``
is emptied because its ``record_id`` names health rows whose ids change here; a sync cursor from before the upgrade
answers 410 and the client resyncs. The other three tombstone tables keep their rows until their parents convert.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: e05703e64861
Revises: 3e7a91d4c0b8
Create Date: 2026-11-12 10:00:00.000000

"""

from collections.abc import Sequence

from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex

# revision identifiers, used by Alembic.
revision: str = "e05703e64861"
down_revision: str | None = "3e7a91d4c0b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_UPDATED_AT_ID = ("user_id", "updated_at", "id")
_USER_DELETED_AT_ID = ("user_id", "deleted_at", "id")

# (table, indexes that contain id), in the order they convert.
_TABLES: tuple[tuple[str, tuple[IdIndex, ...]], ...] = (
    *(
        (table, (IdIndex(f"ix_{table}_user_updated_at_id", _USER_UPDATED_AT_ID),))
        for table in (
            "health_fasting",
            "health_poop",
            "health_sleep",
            "health_steps",
            "health_targets",
            "health_water",
            "health_weight",
        )
    ),
    (
        "health_record_deletions",
        (IdIndex("ix_health_record_deletions_user_deleted_at_id", _USER_DELETED_AT_ID),),
    ),
    ("activity_deletions", (IdIndex("ix_activity_deletions_user_id_deleted_at_id", _USER_DELETED_AT_ID),)),
    ("gear_deletions", (IdIndex("ix_gear_deletions_user_id_deleted_at_id", _USER_DELETED_AT_ID),)),
    (
        "gear_component_deletions",
        (IdIndex("ix_gear_component_deletions_user_id_deleted_at_id", _USER_DELETED_AT_ID),),
    ),
    ("users_goals", ()),
    ("notifications", ()),
    ("followers", (IdIndex("ix_followers_id", ("id",)),)),
    ("follower_blocks", (IdIndex("ix_follower_blocks_id", ("id",)),)),
    ("follow_request_declines", ()),
    ("auth_known_devices", ()),
    ("mfa_factors", ()),
    ("mfa_backup_codes", ()),
    ("rotated_refresh_tokens", ()),
    ("users_integrations", ()),
    ("users_privacy_settings", ()),
    ("users_default_gear", ()),
    ("users_identity_providers", (IdIndex("ix_users_identity_providers_id", ("id",)),)),
    ("idp_session_tokens", ()),
)


def upgrade() -> None:
    """Keep the id order in ``created_at``, empty the unmappable tombstones and convert every primary key."""
    uuid_conversion.add_created_at_in_id_order("users_goals", comment="When the goal was created")
    uuid_conversion.keep_created_at_in_id_order("followers")
    uuid_conversion.keep_created_at_in_id_order("follower_blocks")
    uuid_conversion.empty_tombstones("health_record_deletions")
    for table, indexes in _TABLES:
        uuid_conversion.give_uuid_primary_key(table, indexes)


def downgrade() -> None:
    """Refuse: the integer ids are gone.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError(
        "Revision 87 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
