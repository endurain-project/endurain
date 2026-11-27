"""Activity restore for the profile data import.

Stages the archived activities, then their components one archive entry at a time, so a single entry of
component records is held however many activities the archive lists. The retained source files and the media are
written after the import has committed, because their storage keys name the restored activity ids.
"""

import os
import uuid
from collections import defaultdict
from typing import Any

import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_profile_transfer.constants as constants
import modules.activities.contributor_registry as activities_contributor_registry
import modules.gears.gear.constants as gear_constants
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def restore_profile(ctx: users_profile_contracts.ProfileImportContext) -> users_profile_contracts.RestoreFiles | None:
    """Stage the archived activities and their components.

    Args:
        ctx: The import context; the restored gear ids are read from it.

    Returns:
        The work that writes the activities' files and media once the rows are committed, or ``None``
        when the archive has none.

    Raises:
        ActivityLimitError: If the archive lists too many activities.
        FileSizeError: If an entry or the archive exceeds the allowed size.
        ImportTimeoutError: If the import runs out of time.
        MemoryAllocationError: If the memory limit is exceeded.
    """
    _report_zero_counts(ctx.counts)
    _restore_global_components(ctx)

    ctx.check_timeout()
    restored = _restore_activities(ctx, ctx.ids.get(gear_constants.PROFILE_ARCHIVE_KEY, {}))
    _restore_activity_components(ctx, restored)
    activities_id_mapping = {archived_id: activity.id for archived_id, activity in restored.items()}

    folders = (constants.ACTIVITY_FILES_FOLDER, constants.ACTIVITY_MEDIA_FOLDER)
    if not any(name.startswith(folders) for name in ctx.archive.names):
        return None

    def restore_files() -> None:
        """Write the archived activity files and media under the restored activity ids."""
        _restore_activity_files(ctx, activities_id_mapping)
        _restore_activity_media(ctx, activities_id_mapping)

    return restore_files


def _report_zero_counts(counts: dict[str, int]) -> None:
    """Report every count the section owns as zero, so an empty import still names them.

    Args:
        counts: Imported item counts.
    """
    counts["activities"] = 0
    counts["activity_files"] = 0
    counts["media"] = 0
    for contributor in activities_contributor_registry.profile_activity_contributors():
        counts[contributor.count_key] = 0
    for global_contributor in activities_contributor_registry.profile_global_contributors():
        counts[global_contributor.count_key] = 0


def _restore_global_components(ctx: users_profile_contracts.ProfileImportContext) -> None:
    """Load and restore every global activity contribution once.

    Args:
        ctx: The import context.
    """
    for contributor in activities_contributor_registry.profile_global_contributors():
        records = ctx.archive.load_json(contributor.archive_path, check_memory=False)
        ctx.counts[contributor.count_key] += contributor.restore(records, ctx.db)
    logger.debug("Restored the global activity components", extra=core_logger.context(user_id=ctx.user_id))


def _restore_activities(
    ctx: users_profile_contracts.ProfileImportContext, gears_id_mapping: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, activity_schema.ActivityRead]:
    """Restore the archived activities, without their components.

    Args:
        ctx: The import context.
        gears_id_mapping: Mapping of old to new gear IDs.

    Returns:
        The restored activities, keyed by their archived IDs.

    Raises:
        ActivityLimitError: If too many activities.
        ImportTimeoutError: If operation times out.
    """
    restored: dict[uuid.UUID, activity_schema.ActivityRead] = {}

    activities_data = ctx.archive.load_json(constants.ACTIVITIES_PATH)
    if not activities_data:
        logger.debug("No activities data to import")
        return restored

    ctx.check_activity_count(len(activities_data))

    batch_size = ctx.batch_size
    for batch_start in range(0, len(activities_data), batch_size):
        ctx.check_timeout()

        for activity_data in activities_data[batch_start : batch_start + batch_size]:
            archived_gear_id = users_profile_contracts.archived_id(activity_data.get("gear_id"))
            activity_data["gear_id"] = gears_id_mapping.get(archived_gear_id) if archived_gear_id else None

            original_activity_id = users_profile_contracts.archived_id(activity_data.get("id"))
            fields = {
                key: value
                for key, value in users_profile_contracts.without_row_identity(activity_data).items()
                if key not in constants.ACTIVITY_READ_FIELDS
            }

            activity = activity_contracts.ActivityCore(**fields, user_id=ctx.user_id)
            # Bulk restore deliberately does not publish activity.created;
            # see integration_service.restore_activity for why.
            new_activity = activity_integration.restore_activity(activity, ctx.db)

            if original_activity_id is not None and new_activity.id is not None:
                restored[original_activity_id] = new_activity

            ctx.counts["activities"] += 1

        ctx.check_memory(f"activities batch {batch_start // batch_size + 1}")

    logger.debug("Imported activities", extra=core_logger.context(count=ctx.counts["activities"]))
    return restored


def _restore_activity_components(
    ctx: users_profile_contracts.ProfileImportContext, restored: dict[uuid.UUID, activity_schema.ActivityRead]
) -> None:
    """Restore the contributed components of the restored activities.

    Each archive entry is read once and held alone: reading it again would count it again against the archive-wide
    size limit.

    Args:
        ctx: The import context.
        restored: The restored activities, keyed by their archived IDs.

    Raises:
        FileSizeError: If an entry or the archive exceeds the allowed size.
        ImportTimeoutError: If operation times out.
        MemoryAllocationError: If the memory limit is exceeded.
    """
    if not restored:
        return

    for contributor in activities_contributor_registry.profile_activity_contributors():
        if contributor.split:
            entries = _get_split_files_list(ctx.archive.names, contributor.archive_path.removesuffix(".json"))
        else:
            entries = [contributor.archive_path]

        for position, entry in enumerate(entries, start=1):
            ctx.check_timeout()
            records = (
                ctx.archive.load_json_part(entry)
                if contributor.split
                else ctx.archive.load_json(entry, check_memory=False)
            )
            for archived_id, activity_records in _group_by_activity(records).items():
                if new_activity := restored.get(archived_id):
                    ctx.counts[contributor.count_key] += contributor.restore(
                        activity_records, archived_id, new_activity, ctx.db
                    )
            del records
            ctx.check_memory(f"{contributor.key} part {position}")


def _group_by_activity(records: list[dict[str, Any]]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Group component records by the archived activity they belong to.

    Args:
        records: The records of one archive entry.

    Returns:
        The records of each activity, in the order the entry lists them; a record naming no activity is left out.
    """
    grouped: defaultdict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if archived_id := users_profile_contracts.archived_id(record.get("activity_id")):
            grouped[archived_id].append(record)
    return grouped


def _get_split_files_list(file_list: frozenset[str], base_filename: str) -> list[str]:
    """Get list of split component files from the archive.

    Args:
        file_list: Set of all entry names in the archive.
        base_filename: Base filename without extension.

    Returns:
        Sorted list of matching entry names.
    """
    split_files = sorted([f for f in file_list if f.startswith(f"{base_filename}_") and f.endswith(".json")])
    if split_files:
        return split_files
    # Fall back to single file if no split files found
    single_file = f"{base_filename}.json"
    if single_file in file_list:
        return [single_file]
    return []


def _restore_activity_files(
    ctx: users_profile_contracts.ProfileImportContext, activities_id_mapping: dict[uuid.UUID, uuid.UUID]
) -> None:
    """Extract and store the archived activity files under the restored ids.

    Args:
        ctx: The import context.
        activities_id_mapping: Mapping of old to new IDs.
    """
    ctx.check_memory("activity files import")

    for file_path in ctx.archive.names:
        path = file_path.replace("\\", "/")

        if path.lower().endswith((".gpx", ".fit", ".tcx")) and path.startswith(constants.ACTIVITY_FILES_FOLDER):
            archived_file_id = users_profile_contracts.archived_id(os.path.splitext(os.path.basename(path))[0])
            ext = os.path.splitext(path)[1]
            new_id = activities_id_mapping.get(archived_file_id) if archived_file_id else None

            if new_id is None:
                continue

            new_file_name = f"{new_id}{ext}"

            # Read bytes from the archive, validate as an activity file, then
            # persist through the platform StorageProvider (the same store
            # the ingestion path writes to) rather than the local
            # processed directory.
            activity_limit = file_uploads.file_validator.config.limits.max_activity_file_size
            file_bytes = ctx.archive.read_bytes(file_path, max_bytes=activity_limit)
            try:
                file_uploads.validate_bytes_sync(
                    file_bytes,
                    kind=file_uploads.UploadKind.ACTIVITY,
                    filename=new_file_name,
                )
            except core_exceptions.DomainError as err:
                logger.warning(
                    "Profile import dropped an invalid activity file",
                    extra=core_logger.context(file_name=new_file_name, detail=err.detail),
                )
                continue
            activity_file_storage_integration.store_activity_file(new_id, ext, file_bytes, ctx.storage)
            ctx.counts["activity_files"] += 1


def _restore_activity_media(
    ctx: users_profile_contracts.ProfileImportContext, activities_id_mapping: dict[uuid.UUID, uuid.UUID]
) -> None:
    """Extract and store the archived activity media under the restored ids.

    Args:
        ctx: The import context.
        activities_id_mapping: Mapping of old to new IDs.
    """
    ctx.check_memory("activity media import")

    for file_path in ctx.archive.names:
        path = file_path.replace("\\", "/")

        if not path.startswith(constants.ACTIVITY_MEDIA_FOLDER):
            continue

        base_name, ext = os.path.splitext(os.path.basename(path))
        if ext.lower() not in file_uploads.IMAGE_CONTENT_TYPES:
            _log_skipped_media("unsupported image type")
            continue
        if "_" not in base_name:
            _log_skipped_media("unexpected file name")
            continue

        orig_id_str, suffix = base_name.split("_", 1)
        archived_media_id = users_profile_contracts.archived_id(orig_id_str)
        new_id = activities_id_mapping.get(archived_media_id) if archived_media_id else None
        if new_id is None:
            _log_skipped_media("not an imported activity")
            continue

        new_file_name = f"{new_id}_{suffix}{ext}"

        # Read bytes from the archive and validate them as an image
        # before storing, then write through the platform
        # StorageProvider under the media area (the same place
        # an upload lands) rather than to a local directory.
        image_limit = file_uploads.file_validator.config.limits.max_image_size
        file_bytes = ctx.archive.read_bytes(file_path, max_bytes=image_limit)
        try:
            file_uploads.validate_bytes_sync(
                file_bytes,
                kind=file_uploads.UploadKind.IMAGE,
                filename=new_file_name,
            )
        except core_exceptions.DomainError as err:
            logger.warning(
                "Profile import dropped invalid activity media",
                extra=core_logger.context(file_name=new_file_name, detail=err.detail),
            )
            continue
        activity_media_integration.store_media_blob(new_id, suffix, ext, file_bytes, ctx.storage)
        ctx.counts["media"] += 1


def _log_skipped_media(reason: str) -> None:
    """Warn that an archived media file was not restored, so its record is left without a file.

    Args:
        reason: Why the file was skipped.
    """
    logger.warning("Profile import skipped an activity media file", extra=core_logger.context(reason=reason))
