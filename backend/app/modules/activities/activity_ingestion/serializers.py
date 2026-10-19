"""ORM↔schema transformation for activity ingestion jobs.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


def to_read_schema(
    orm_job: activity_ingestion_models.ActivityIngestionJob,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Convert an ORM ``ActivityIngestionJob`` row to its read schema.

    Args:
        orm_job: The ORM model instance.

    Returns:
        The job's read schema.
    """
    return activity_ingestion_schema.ActivityIngestionJobRead(
        id=orm_job.id,
        kind=activity_ingestion_constants.IngestionJobKind(orm_job.kind),
        filename=orm_job.filename,
        import_source=orm_job.import_source,
        files_total=orm_job.files_total,
        files_done=orm_job.files_done,
        files_failed=orm_job.files_failed,
        provider=orm_job.provider,
        status=activity_ingestion_constants.IngestionJobStatus(orm_job.status),
        error_code=(
            activity_ingestion_constants.IngestionJobErrorCode(orm_job.error_code) if orm_job.error_code else None
        ),
        activity_ids=list(orm_job.activity_ids or []),
        created_at=orm_job.created_at,
        updated_at=orm_job.updated_at,
        completed_at=orm_job.completed_at,
    )
