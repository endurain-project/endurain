"""Activity restore for the profile data import.

Stages the archived activities and their components in batches, so memory stays bounded however many
activities the archive lists. The retained source files and the media are written after the import has
committed, because they attach to the restored activity ids.
"""

import hashlib
import os
import uuid
from typing import Any

import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import core.timezone as core_timezone
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
    counts["activities_skipped"] = 0
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

    The activities that are not legs are restored first, so each leg finds its parent's new id in the mapping. A
    leg whose parent is not in the archive is restored as a top-level activity.

    An activity the account already has is skipped, with its legs and components: one that holds one of its sources
    (the same file or provider activity), or that is of the same effort as an activity of the account's own, as an
    import of a file would see it. What a restore stored itself does not count, so an archive that lists one effort
    twice restores both. The skips are counted as ``activities_skipped``.

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
    #: The archived ids of the activities the account already has, which are not restored.
    skipped: set[uuid.UUID] = set()

    activities_data = ctx.archive.load_json(constants.ACTIVITIES_PATH)
    if not activities_data:
        logger.debug("No activities data to import")
        return activities_id_mapping

    ctx.check_activity_count(len(activities_data))
    activities_data.sort(key=lambda row: row.get(constants.ACTIVITY_PARENT_FIELD) is not None)

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

        _derive_provider_sources(batch_components, activities_batch)

        for activity_data in activities_batch:
            archived_gear_id = users_profile_contracts.archived_id(activity_data.get("gear_id"))
            activity_data["gear_id"] = gears_id_mapping.get(archived_gear_id) if archived_gear_id else None

            original_activity_id = users_profile_contracts.archived_id(activity_data.get("id"))
            archived_parent_id = users_profile_contracts.archived_id(activity_data.get(constants.ACTIVITY_PARENT_FIELD))
            fields = {
                key: value
                for key, value in users_profile_contracts.without_row_identity(activity_data).items()
                if key not in constants.ACTIVITY_READ_FIELDS and key != constants.ACTIVITY_PARENT_FIELD
            }

            activity = activity_contracts.ActivityCore(**fields, user_id=ctx.user_id)
            if _is_already_held(
                ctx,
                activity,
                original_activity_id,
                archived_parent_id,
                batch_components,
                activities_id_mapping,
                skipped,
            ):
                # The account has this activity, so neither it nor what hangs off it is restored.
                if original_activity_id is not None:
                    skipped.add(original_activity_id)
                ctx.counts["activities_skipped"] += 1
                continue
            # Bulk restore deliberately does not publish activity.created;
            # see integration_service.restore_activity for why.
            new_activity = activity_integration.restore_activity(
                activity,
                ctx.db,
                parent_activity_id=activities_id_mapping.get(archived_parent_id) if archived_parent_id else None,
            )

            if original_activity_id is not None and new_activity.id is not None:
                activities_id_mapping[original_activity_id] = new_activity.id
                _restore_activity_components(ctx, batch_components, original_activity_id, new_activity)

            ctx.counts["activities"] += 1

        del batch_components
        ctx.check_memory(f"activities batch {batch_start // batch_size + 1}")

    logger.debug("Imported activities", extra=core_logger.context(count=ctx.counts["activities"]))
    return activities_id_mapping


def _is_already_held(
    ctx: users_profile_contracts.ProfileImportContext,
    activity: activity_contracts.ActivityCore,
    original_activity_id: uuid.UUID | None,
    archived_parent_id: uuid.UUID | None,
    batch_components: dict[str, list[dict[str, Any]]],
    activities_id_mapping: dict[uuid.UUID, uuid.UUID],
    skipped: set[uuid.UUID],
) -> bool:
    """Tell whether the account already has an archived activity.

    A leg follows its parent: it is skipped with a skipped parent and restored with a restored one. Any other
    activity, a leg whose parent is not in the archive included, is matched by its sources and by its effort.

    Args:
        ctx: The import context.
        activity: The archived activity.
        original_activity_id: Its archived id.
        archived_parent_id: The archived id of its multisport parent, if it is a leg.
        batch_components: Records of the batch keyed by profile contributor key, with the sources of its activities.
        activities_id_mapping: The archived ids restored so far, and their new ids.
        skipped: The archived ids skipped so far.

    Returns:
        ``True`` when the account has it.
    """
    if archived_parent_id is not None and archived_parent_id in skipped:
        return True
    if archived_parent_id is not None and archived_parent_id in activities_id_mapping:
        return False
    sources = [
        activity_contracts.NewSource(
            record.kind, record.provider_id, record.file_sha256, record.session_start, record.precedence
        )
        for record in (
            activity_contracts.SourceArchiveRecord.model_validate(raw)
            for raw in batch_components.get(constants.SOURCES_COMPONENT_KEY, [])
            if original_activity_id is not None
            and users_profile_contracts.archived_id(raw.get("activity_id")) == original_activity_id
        )
    ]
    return activity_integration.restore_matches_existing(
        ctx.user_id, activity, sources, ctx.db, exclude=set(activities_id_mapping.values())
    )


def _derive_provider_sources(
    batch_components: dict[str, list[dict[str, Any]]], activities_batch: list[dict[str, Any]]
) -> None:
    """Add the provider sources an archive written before sources existed leaves out.

    An activity that has no archived source and carries a Strava or Garmin Connect id takes a source from that id, as it
    held one when it was imported. A leg of a multisport activity takes it with its own start, as a leg's source has.

    Args:
        batch_components: Records keyed by profile contributor key; the derived sources are added to ``sources``.
        activities_batch: The archived activities of the batch.
    """
    sources = batch_components.setdefault(constants.SOURCES_COMPONENT_KEY, [])
    archived = {users_profile_contracts.archived_id(record.get("activity_id")) for record in sources}
    for activity_data in activities_batch:
        original_activity_id = users_profile_contracts.archived_id(activity_data.get("id"))
        if original_activity_id is None or original_activity_id in archived:
            continue
        is_leg = activity_data.get(constants.ACTIVITY_PARENT_FIELD) is not None
        start = core_timezone.to_utc_aware(activity_data.get("start_time")) if is_leg else None
        for kind, field, precedence in constants.PROVIDER_ID_SOURCES:
            if activity_data.get(field) is not None:
                sources.append(
                    {
                        "activity_id": str(original_activity_id),
                        "kind": kind,
                        "provider_id": activity_data[field],
                        "session_start": start.replace(microsecond=0).isoformat() if start is not None else None,
                        "precedence": precedence,
                    }
                )


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
            _attach_activity_file(ctx, new_id, ext, file_bytes)


def _attach_activity_file(
    ctx: users_profile_contracts.ProfileImportContext, activity_id: uuid.UUID, extension: str, file_bytes: bytes
) -> None:
    """Retain a restored activity's file and attach it to the activity in its own short transaction.

    Runs once the restored rows are committed. Identical archived files share one row. An activity that has no source
    yet takes the file's as its own. A file that turns out to have
    no activity to attach to is removed again when this call created its row.

    Args:
        ctx: The import context.
        activity_id: The restored activity.
        extension: The file's extension.
        file_bytes: The file's bytes.
    """
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    staged = activity_file_storage_integration.stage_file(ctx.user_id, sha256, extension, file_bytes, ctx.storage)
    with core_database.SessionLocal() as db:
        attached = activity_integration.set_file_id(activity_id, staged.ref.file_id, db)
        if attached:
            activity_file_storage_integration.mark_attached(staged.ref.file_id, db)
            # An archive written before sources existed carries none, so the file identifies the activity; one that
            # has a source keeps it.
            activity_integration.add_restored_file_source(activity_id, extension, sha256, db)
        db.commit()
    logger.debug(
        "Retained the source file of a restored activity",
        extra=core_logger.context(activity_id=activity_id, file_id=staged.ref.file_id, attached=attached),
    )
    if attached:
        ctx.counts["activity_files"] += 1
    elif staged.created:
        activity_file_storage_integration.release_unattached(staged.ref.file_id, ctx.storage)


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
