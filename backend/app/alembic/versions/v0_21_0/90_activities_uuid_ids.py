"""90: activities and their child tables get UUID ids

``activities.id`` and the ids of its child tables (``activity_laps``, ``activity_media``, ``activity_sets``,
``activities_streams`` and ``activity_workout_steps``) become random ``uuid`` values, and so do the five
``activity_id`` columns that hold an activity id. Their foreign keys (``ON DELETE CASCADE``), indexes, the unique index
``uq_activity_media_activity_content_hash`` and comments are recreated under the same names.

``activity_media`` gets ``created_at``, filled in the old id order, so the order of the photos of an activity
survives. Laps, sets and workout steps sort by ``start_time`` or ``message_index`` and then by id.

``activity_deletions`` is emptied: its ``record_id`` names rows whose ids change, and a sync cursor from before the
upgrade answers 410.

The ids stored in event payloads and metadata, notification options and ingestion jobs are rewritten as UUID strings,
the shape ``model_dump(mode="json")`` writes: the ``activity_id`` of ``activity.created``, ``activity.updated`` and
``activity.deleted`` in the event outbox, the processing jobs (every status, dead letters included) and the event log;
the ``activity_id`` of the event metadata; the ``activity_id`` of the notification options; and the elements of
``activity_ingestion_jobs.activity_ids``. A null or a string is kept. The ``SCHEMA_VERSION`` of the payload classes
stays: this revision is the same one-time exception as revisions 85 and 88 describe for every conversion revision.
The ``user_id`` fields stay integers until the users revision. An id that names no activity (an activity deleted
before) becomes a fresh random UUID: still a valid id, matching nothing.

The provider ids (``strava_activity_id``, ``garminconnect_activity_id``, ``strava_activity_stream_id``) and the FIT
enum integers are untouched, and ``activity_exercise_titles`` keeps its integer id. Audit rows are not rewritten.

The stored files are named by the integer ids: the map thumbnails (``map_thumbnail_path``), the activity files and
the media (``media_path``). The columns keep their integer-layout values here and data migration 13, which this
revision registers as not executed, renames the files and rewrites the columns. The revision cannot do it: data
migration 12 runs before migration 13 on a v0.20.x upgrade and reads those columns in the integer layout. Every
activity's old and new id is recorded in ``uuid_migration_ids`` for it, and migration 13 drops the table afterwards.

Expected cost, on a large install: ``activities`` is rewritten once (the ``new_id`` fill), then scanned for ``NOT NULL``
and indexed (primary key and ``ix_activities_user_id_updated_at_id``). Each child table is rewritten exactly once (the
fused ``new_id`` and ``new_activity_id`` fill; ``activities_streams`` is the large one, and its out-of-line
``stream_waypoints`` values are not copied when unchanged, which is unverified on real data), then scanned for
``NOT NULL``, given its primary key and ``activity_id`` index, and its foreign key is validated against the primary
key of ``activities``. ``activity_media`` is rewritten a second time, a small one, for ``created_at``. Every stored
id (event payloads and metadata, notification options, ingestion job arrays) is looked up through the primary key of
``activities``, one index probe per rewritten row, so that part costs O(rewritten rows x log activities). Dropped
columns are metadata-only. The dead tuples of the rewrites roughly double the heap until ``VACUUM``: run
``VACUUM (ANALYZE)`` afterwards.

The revision runs inside the single upgrade transaction and is irreversible.

Revision ID: 3ab6649cdd08
Revises: ecaa46b32646
Create Date: 2026-11-12 13:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex, IdReference

# revision identifiers, used by Alembic.
revision: str = "3ab6649cdd08"
down_revision: str | None = "ecaa46b32646"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARENT = "activities"

_PARENT_INDEXES = (IdIndex("ix_activities_user_id_updated_at_id", ("user_id", "updated_at", "id")),)

#: (payload class, field, event types it is stored under, parent table); every entry is rewritten.
PAYLOAD_ID_REWRITES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("modules.activities.activity.events.ActivityCreatedPayload", "activity_id", ("activity.created",), _PARENT),
    ("modules.activities.activity.events.ActivityUpdatedPayload", "activity_id", ("activity.updated",), _PARENT),
    ("modules.activities.activity.events.ActivityDeletedPayload", "activity_id", ("activity.deleted",), _PARENT),
)

_CHILDREN: tuple[IdReference, ...] = (
    IdReference(
        "activity_laps",
        "activity_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Activity ID that the activity lap belongs",
        indexes=(IdIndex("ix_activity_laps_activity_id", ("activity_id",)),),
    ),
    IdReference(
        "activity_media",
        "activity_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Activity ID that the activity media belongs",
        indexes=(IdIndex("ix_activity_media_activity_id", ("activity_id",)),),
    ),
    IdReference(
        "activity_sets",
        "activity_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Activity ID that the activity lap belongs",
        indexes=(IdIndex("ix_activity_sets_activity_id", ("activity_id",)),),
    ),
    IdReference(
        "activities_streams",
        "activity_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Activity ID that the activity stream belongs",
        indexes=(IdIndex("ix_activities_streams_activity_id", ("activity_id",)),),
    ),
    IdReference(
        "activity_workout_steps",
        "activity_id",
        nullable=False,
        ondelete="CASCADE",
        comment="Activity ID that the activity workout steps belongs",
        indexes=(IdIndex("ix_activity_workout_steps_activity_id", ("activity_id",)),),
    ),
)

#: The child tables whose own ``id`` becomes a UUID; no index of theirs contains ``id``.
_CHILD_PRIMARY_KEYS = tuple(child.table for child in _CHILDREN)


def upgrade() -> None:
    """Order the photos, empty the tombstones, rewrite the stored ids and swap the activity ids for UUIDs."""
    uuid_conversion.add_created_at_in_id_order("activity_media", comment="When the media record was created")
    uuid_conversion.empty_tombstones("activity_deletions")
    uuid_conversion.add_uuid_ids_with_child_tables(_PARENT, _CHILDREN)
    for _payload_class, field, event_types, parent in PAYLOAD_ID_REWRITES:
        uuid_conversion.rewrite_payload_ids(event_types, field, parent, by_primary_key=True)
    uuid_conversion.rewrite_metadata_ids("activity_id", _PARENT, by_primary_key=True)
    uuid_conversion.rewrite_notification_option_ids("activity_id", _PARENT, by_primary_key=True)
    uuid_conversion.rewrite_json_array_ids("activity_ingestion_jobs", "activity_ids", _PARENT)
    uuid_conversion.record_old_ids(_PARENT)
    uuid_conversion.schedule_stored_key_renames()
    uuid_conversion.swap_in_uuid_ids(_PARENT, _PARENT_INDEXES, _CHILDREN)
    for table in _CHILD_PRIMARY_KEYS:
        uuid_conversion.swap_in_uuid_primary_key(table)
    op.create_index(
        "uq_activity_media_activity_content_hash", "activity_media", ["activity_id", "content_hash"], unique=True
    )


def downgrade() -> None:
    """Refuse: the integer ids are gone.

    Raises:
        NotImplementedError: Always.
    """
    raise NotImplementedError(
        "Revision 90 cannot be reversed: restore the database from the backup taken before the upgrade."
    )
