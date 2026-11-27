"""Operations other modules may call on the profile import and export."""

import uuid

import jasil.providers as platform_providers

import core.job_status as core_job_status
import modules.users.users_profile.export_job_service as profile_export_job_service
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.import_job_service as profile_import_job_service
import modules.users.users_profile.import_state_store as profile_import_state_store
import modules.users.users_profile.schema as profile_schema
import modules.users.users_profile.transfer_pool as profile_transfer_pool


def delete_staged_transfers(user_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Delete the archives staged for a user's profile export and imports.

    Housekeeping for a deleted account: a storage failure is logged, and the scheduled sweep
    removes whatever is left.

    Args:
        user_id: The user whose staged archives to remove.
        storage: The platform storage provider.
    """
    profile_export_job_service.discard_staged_export(user_id, storage)
    profile_import_job_service.discard_staged_imports(user_id, storage)


def shutdown_transfer_pool() -> None:
    """Stop the in-process pool profile imports and exports run on, without waiting for them."""
    profile_transfer_pool.pool.shutdown()


def read_export_job(
    job: core_job_status.JobRef, state: platform_providers.StateProvider
) -> profile_schema.ProfileExportStatus | None:
    """Read the profile export a job reference names.

    Args:
        job: The job's reference.
        state: The platform state provider.

    Returns:
        The export's status, or None when its record is gone or belongs to a later export.
    """
    read = profile_export_state_store.ProfileExportStateStore(state).read_job(job)
    return profile_export_job_service.export_status(*read) if read is not None else None


def read_import_job(
    job: core_job_status.JobRef, state: platform_providers.StateProvider
) -> profile_schema.ProfileImportStatus | None:
    """Read the profile import a job reference names.

    Args:
        job: The job's reference.
        state: The platform state provider.

    Returns:
        The import's status, or None when its record is gone or belongs to a later import.
    """
    read = profile_import_state_store.ProfileImportStateStore(state).read_job(job)
    return profile_import_job_service.import_status(*read) if read is not None else None
