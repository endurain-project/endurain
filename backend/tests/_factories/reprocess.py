"""Activities stored by the real ingestion and then made to look like an older analysis stored them."""

import dataclasses
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import modules.activities.activity.models as activity_models
import modules.activities.activity_file_storage.constants as file_storage_constants
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_laps.models as lap_models
import modules.activities.activity_sets.models as set_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.models as stream_models
import modules.activities.activity_workout_steps.models as step_models
from tests._factories.ingestion import retained_file, store_legacy_file

FIXTURES = Path(__file__).parents[1] / "activities" / "activity_file_import" / "fixtures"
RUN = FIXTURES / "outdoor_run" / "24273515840_ACTIVITY.fit"
STRENGTH = FIXTURES / "strength" / "24939814804_ACTIVITY.fit"
TRIATHLON = FIXTURES / "triathlon" / "24846754341_ACTIVITY.fit"
TREADMILL = FIXTURES / "treadmill_run" / "24280055123_ACTIVITY.fit"

OLD = datetime(2020, 1, 1, tzinfo=UTC)

#: Derived values no analysis would compute for the fixtures, so a reprocess that rewrites them shows.
BOGUS_DERIVED = {
    "distance": 1,
    "end_time": OLD,
    "timezone": "Etc/GMT",
    "total_elapsed_time": 1,
    "total_timer_time": 1,
    "elevation_gain": 999,
    "elevation_loss": 999,
    "pace": 9,
    "average_speed": 9,
    "max_speed": 9,
    "average_power": 999,
    "max_power": 999,
    "normalized_power": 999,
    "average_hr": 99,
    "max_hr": 99,
    "average_cad": 99,
    "max_cad": 99,
    "workout_feeling": 1,
    "workout_rpe": 10,
    "calories": 1,
    "tracker_manufacturer": "old",
    "tracker_model": "old",
    "total_cycles": 1,
    "start_latitude": 1.0,
    "start_longitude": 1.0,
}


def import_fixture(db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage) -> list[uuid.UUID]:
    """Import a fixture file through the real pipeline and return the stored top-level activity ids.

    Args:
        db: Database session; the import is committed.
        user_id: The importing user.
        source: The fixture file.
        tmp_path: A directory the file is staged in.
        storage: The platform storage provider the file is retained in.

    Returns:
        The ids of the activities the file stored, a multisport parent for a group.
    """
    staged = tmp_path / f"{uuid.uuid4().hex}{source.suffix}"
    shutil.copyfile(source, staged)
    created = pipeline_service.validate_prepare_and_store_file(
        user_id, str(staged), db, source=ingestion_contracts.UploadSource(), storage=storage
    )
    db.commit()
    assert created
    return [activity.id for activity in created]


def degrade(db: Session, activity_id: uuid.UUID) -> None:
    """Make an activity look like one an older analysis stored: version 0, old values, an extra child of each kind.

    Args:
        db: Database session; the change is committed.
        activity_id: The activity to degrade.
    """
    db.execute(
        update(activity_models.Activity)
        .where(activity_models.Activity.id == activity_id)
        .values(**BOGUS_DERIVED, analysis_version=0, updated_at=OLD)
    )
    db.execute(delete(stream_models.ActivitySamples).where(stream_models.ActivitySamples.activity_id == activity_id))
    db.add_all(
        [
            stream_models.ActivitySamples(activity_id=activity_id, offsets_ms=[0], heart_rate=[1]),
            stream_models.ActivityStreams(
                activity_id=activity_id,
                stream_type=stream_constants.STREAM_TYPE_HR,
                stream_waypoints=[{"time": "2000-01-01T00:00:00", "hr": 1}],
            ),
            lap_models.ActivityLaps(activity_id=activity_id, start_time=OLD, total_distance=1),
            set_models.ActivitySets(activity_id=activity_id, duration=1, set_type="old", start_time=OLD, repetitions=1),
            step_models.ActivityWorkoutSteps(activity_id=activity_id, message_index=99),
        ]
    )
    db.commit()


def store_as_legacy_files(db: Session, activity_ids: list[uuid.UUID], storage) -> None:
    """Move the files of activities to the layout used before file rows: one copy per activity, no row.

    Args:
        db: Database session; the change is committed.
        activity_ids: The activities whose retained files become legacy copies under ``processed/{activity id}``.
        storage: The platform storage provider the files are retained in.
    """
    copies = {activity_id: retained_file(activity_id, storage) for activity_id in activity_ids}
    refs = list(db.scalars(select(file_models.ActivityFile)).all())
    for activity_id, copy in copies.items():
        assert copy is not None
        store_legacy_file(activity_id, copy[1], storage, extension=copy[0])
    db.execute(
        update(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids)).values(file_id=None)
    )
    db.execute(delete(file_models.ActivityFile))
    db.commit()
    for ref in refs:
        storage.delete(file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, ref.storage_key)


def import_legacy_legs(
    db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage, monkeypatch
) -> list[uuid.UUID]:
    """Import a multi-session file the way it was stored before groups: one activity and one file copy per session."""
    real = pipeline_service.parse_file

    def without_a_parent(*args, **kwargs):
        return dataclasses.replace(real(*args, **kwargs), parent=None)

    with monkeypatch.context() as patch:
        patch.setattr(pipeline_service, "parse_file", without_a_parent)
        activity_ids = import_fixture(db, user_id, source, tmp_path, storage)
    store_as_legacy_files(db, activity_ids, storage)
    return activity_ids


def start_ordered(db: Session, activity_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Return the activities in start order."""
    db.expire_all()
    return list(
        db.execute(
            select(activity_models.Activity.id)
            .where(activity_models.Activity.id.in_(activity_ids))
            .order_by(activity_models.Activity.start_time)
        ).scalars()
    )
