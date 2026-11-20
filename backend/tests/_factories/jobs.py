"""Background jobs as the application stores them, for tests on the real database."""

import uuid

import jasil.runtime as jasil_runtime
from sqlalchemy.orm import Session

import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.schema as ingestion_schema


def make_ingestion_job(db: Session, user_id: uuid.UUID) -> ingestion_schema.ActivityIngestionJobRead:
    """Stage a pending activity upload job through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user who started the job.

    Returns:
        The staged job.
    """
    return ingestion_crud.create_ingestion_job(
        uuid.uuid4(), user_id, ingestion_constants.IngestionJobKind.UPLOAD, db, filename="ride.fit"
    )


def make_bulk_edit_job(user_id: uuid.UUID) -> uuid.UUID:
    """Queue a bulk visibility edit in the platform state store, as the route does, without running it.

    Args:
        user_id: The user who started the edit.

    Returns:
        The job's id.
    """
    states = bulk_edit_state_store.ActivityBulkEditStateStore(jasil_runtime.get_active_platform().state)
    return states.begin(user_id, bulk_edit_constants.BulkEditKind.VISIBILITY, conflict="A bulk edit is in progress").id
