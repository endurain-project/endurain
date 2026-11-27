"""Activities stored by the real ingestion and then made to look like an older analysis stored them."""

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_laps.models as lap_models
import modules.activities.activity_sets.models as set_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.models as stream_models
import modules.activities.activity_workout_steps.models as step_models

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
