"""Activity restore for the profile data import.

Stages the archived activities and their components in batches, so memory stays bounded however many
activities the archive lists. The retained source files and the media are written after the import has
committed, because their storage keys name the restored activity ids.
"""

import os
import uuid
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
        ImportTimeoutError: If the import runs out of time.
        MemoryAllocationError: If the memory limit is exceeded.
    """
    _report_zero_counts(ctx.counts)
    _restore_global_components(ctx)

    ctx.check_timeout()
    activities_id_mapping = _restore_activities(ctx, ctx.ids.get(gear_constants.PROFILE_ARCHIVE_KEY, {}))

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


def _restore_activity_components(
    ctx: users_profile_contracts.ProfileImportContext,
    component_data: dict[str, list[dict[str, Any]]],
    original_activity_id: uuid.UUID,
    new_activity: activity_schema.ActivityRead,
) -> None:
    """Restore the contributed components for a single restored activity.

    Args:
        ctx: The import context.
        component_data: Records keyed by profile contributor key.
        original_activity_id: Archived ID of the activity.
        new_activity: New activity object.
    """
    for contributor in activities_contributor_registry.profile_activity_contributors():
        ctx.counts[contributor.count_key] += contributor.restore(
            component_data.get(contributor.key, []),
            original_activity_id,
            new_activity,
            ctx.db,
        )


def _restore_activities(
    ctx: users_profile_contracts.ProfileImportContext, gears_id_mapping: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Restore the archived activities in batches to manage memory.

    Args:
        ctx: The import context.
        gears_id_mapping: Mapping of old to new gear IDs.

    Returns:
        Dictionary mapping old activity IDs to new IDs.

    Raises:
        ActivityLimitError: If too many activities.
        ImportTimeoutError: If operation times out.
    """
    activities_id_mapping: dict[uuid.UUID, uuid.UUID] = {}

    activities_data = ctx.archive.load_json(constants.ACTIVITIES_PATH)
    if not activities_data:
        logger.debug("No activities data to import")
        return activities_id_mapping

    ctx.check_activity_count(len(activities_data))

    contributors = activities_contributor_registry.profile_activity_contributors()
    component_files: dict[str, list[str]] = {}
    component_records: dict[str, list[dict[str, Any]]] = {}
    for contributor in contributors:
        if contributor.split:
            component_files[contributor.key] = _get_split_files_list(
                ctx.archive.names,
                contributor.archive_path.removesuffix(".json"),
            )
        else:
            component_records[contributor.key] = ctx.archive.load_json(
                contributor.archive_path,
                check_memory=False,
            )

    logger.debug(
        "Importing activities with batched component loading", extra=core_logger.context(count=len(activities_data))
    )

    batch_size = ctx.batch_size
    for batch_start in range(0, len(activities_data), batch_size):
        ctx.check_timeout()

        batch_end = min(batch_start + batch_size, len(activities_data))
        activities_batch = activities_data[batch_start:batch_end]

        logger.debug(
            "Processing an activities batch",
            extra=core_logger.context(
                batch_number=batch_start // batch_size + 1, batch_start=batch_start, batch_end=batch_end
            ),
        )

        batch_components: dict[str, list[dict[str, Any]]] = {}
        for contributor in contributors:
            if contributor.split:
                batch_components[contributor.key] = _load_components_for_batch(
                    ctx,
                    component_files[contributor.key],
                    activities_batch,
                    contributor.key,
                )
            else:
                batch_components[contributor.key] = _filter_components_for_batch(
                    component_records.get(contributor.key, []),
                    activities_batch,
                )

        for activity_data in activities_batch:
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
                activities_id_mapping[original_activity_id] = new_activity.id
                _restore_activity_components(ctx, batch_components, original_activity_id, new_activity)

            ctx.counts["activities"] += 1

        del batch_components
        ctx.check_memory(f"activities batch {batch_start // batch_size + 1}")

    logger.debug("Imported activities", extra=core_logger.context(count=ctx.counts["activities"]))
    return activities_id_mapping


def _filter_components_for_batch(
    records: list[dict[str, Any]],
    activities_batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter in-memory component records to the current activity batch.

    Args:
        records: Every archived record of the component.
        activities_batch: Activities in the current batch.

    Returns:
        The records that belong to the batch's activities.
    """
    activity_ids = {
        archived
        for activity in activities_batch
        if (archived := users_profile_contracts.archived_id(activity.get("id")))
    }
    return [
        record
        for record in records
        if isinstance(record, dict) and users_profile_contracts.archived_id(record.get("activity_id")) in activity_ids
    ]


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


def _load_components_for_batch(
    ctx: users_profile_contracts.ProfileImportContext,
    component_files: list[str],
    activities_batch: list[dict[str, Any]],
    component_name: str,
) -> list[dict[str, Any]]:
    """Load components only for activities in current batch.

    Args:
        ctx: The import context.
        component_files: List of component file paths.
        activities_batch: Activities in current batch.
        component_name: Name of component type.

    Returns:
        List of component data for batch activities.
    """
    if not component_files:
        return []

    batch_activity_ids = {
        archived
        for activity in activities_batch
        if (archived := users_profile_contracts.archived_id(activity.get("id")))
    }

    all_components = []

    for filename in component_files:
        components = ctx.archive.load_json_part(filename)
        # Only keep components for activities in this batch
        filtered = [
            component
            for component in components
            if users_profile_contracts.archived_id(component.get("activity_id")) in batch_activity_ids
        ]
        all_components.extend(filtered)

        if filtered:
            logger.debug(
                "Loaded components for the batch",
                extra=core_logger.context(
                    count=len(filtered),
                    total_count=len(components),
                    component_name=component_name,
                    filename=filename,
                ),
            )

    return all_components


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

        if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith(constants.ACTIVITY_MEDIA_FOLDER):
            file_name = os.path.basename(path)
            base_name, ext = os.path.splitext(file_name)

            if "_" in base_name:
                orig_id_str, suffix = base_name.split("_", 1)
                archived_media_id = users_profile_contracts.archived_id(orig_id_str)
                new_id = activities_id_mapping.get(archived_media_id) if archived_media_id else None

                if new_id is None:
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
