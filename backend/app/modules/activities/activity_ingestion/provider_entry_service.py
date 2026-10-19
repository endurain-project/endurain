"""Entry point for provider syncs: store one downloaded activity file, never raising.

Garmin Connect downloads a file per activity and hands it here. A failure is logged
and reported as ``None`` so the sync moves on to the next activity instead of
aborting the window. Bulk imports do not come through here: they work a staged
archive in batches (:mod:`bulk_import_service`) and count their own failures.
"""

from pathlib import Path

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.pipeline_service as activity_ingestion_pipeline_service

logger = core_logger.get_logger(__name__)


def store_activity_file(
    token_user_id: int,
    file_path: str,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
) -> list[activity_schema.ActivityRead] | None:
    """Validate an on-disk activity file and persist it, returning ``None`` on failure.

    Supports .gpx, .tcx, .fit, and .gz files. Must be called from a worker thread
    with no running event loop, because file validation runs a private event loop
    internally.

    Args:
        token_user_id: ID of the user the activity belongs to.
        file_path: Absolute path to the activity file to parse.
        storage: The blob-storage provider the source file is retained in.
        db: SQLAlchemy database session.
        source: Where the file came from, and any source-specific metadata.

    Returns:
        List of created activity schema objects, or None if the file could not be
        parsed or persisted.
    """
    try:
        return activity_ingestion_pipeline_service.validate_prepare_and_store_file(
            token_user_id,
            file_path,
            db,
            source=source,
            storage=storage,
        )
    except Exception as err:
        # This entry swallows the failure so the caller's loop continues on the
        # same session, so it is the one that has to leave that session usable.
        db.rollback()
        logger.error(
            "Error in store_activity_file",
            exc_info=err,
            extra=core_logger.context(file=Path(file_path).name, user_id=token_user_id),
        )
        return None
