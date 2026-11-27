"""The ingestion operations the reprocess data migration needs, and nothing else.

Imported only by ``app/migrations``. Each write is a wrapper that owns its commit, which CRUD never performs.
"""

import uuid

import jasil.providers as platform_providers

import modules.activities.activity_ingestion.reprocess_service as activity_ingestion_reprocess_service

ReprocessOutcome = activity_ingestion_reprocess_service.ReprocessOutcome


def reprocess_activity(activity_id: uuid.UUID, storage: platform_providers.StorageProvider) -> ReprocessOutcome:
    """Recompute one activity from its retained file and write it over the stored values.

    Opens its own short sessions, so none is held while the file is read or parsed, and commits one transaction per
    activity (a multisport activity with its legs). It publishes no event. An activity with no retained file, no
    session that starts where it does, or an unreadable file is left exactly as it was.

    Args:
        activity_id: The activity to reprocess.
        storage: The blob-storage provider the source file is retained in.

    Returns:
        What was done.
    """
    return activity_ingestion_reprocess_service.reprocess_activity(activity_id, storage)
