"""Activity collection for the profile data export.

Streams the user's activities and their components (laps, sets, streams, workout steps, media
records, file-global records) into the export archive a page or batch at a time, so memory stays
bounded however many activities the user has. The retained source files and the media blobs are
read from storage after the export's read transaction is committed.
"""

from collections.abc import Callable, Iterator, Sequence

from pydantic import BaseModel
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.activity_profile_transfer.constants as constants
import modules.activities.contributor_registry as activities_contributor_registry
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def export_profile(ctx: users_profile_contracts.ProfileExportContext) -> users_profile_contracts.ExportFiles | None:
    """Write the user's activities and their components into the archive.

    The activities are read a page at a time and written as they arrive, so no more than one page
    is held, however many the user has. A page that cannot be read fails the export: skipping it
    would leave activities out of an archive that still reports itself complete.

    Args:
        ctx: The export context.

    Returns:
        The work that writes the activities' files and media once the read transaction is committed,
        or ``None`` when the user has no activities.
    """
    _report_zero_counts(ctx.counts)
    ctx.check_memory("activity collection start")
    logger.debug("Starting batched activity collection", extra=core_logger.context(batch_size=ctx.batch_size))

    activity_ids: list[int] = []
    ctx.archive.write_json_stream(constants.ACTIVITIES_PATH, _iter_activity_batches(activity_ids, ctx))
    logger.debug("Written activities to the archive", extra=core_logger.context(count=len(activity_ids)))

    if activity_ids:
        _write_activity_components(ctx, activity_ids)
    else:
        logger.debug("No activities found for the user", extra=core_logger.context(user_id=ctx.user_id))

    _write_global_components(ctx)

    if not activity_ids:
        return None

    def write_files() -> None:
        """Write the activities' retained source files and media."""
        _write_activity_files(ctx, activity_ids)
        ctx.check_timeout()
        _write_activity_media(ctx, activity_ids)

    return write_files


def _report_zero_counts(counts: dict[str, int]) -> None:
    """Report every count the section owns as zero, so an empty export still names them.

    Args:
        counts: Exported item counts.
    """
    counts["activities"] = 0
    counts["activity_files"] = 0
    counts["media"] = 0
    for contributor in activities_contributor_registry.profile_activity_contributors():
        counts[contributor.count_key] = 0
    for global_contributor in activities_contributor_registry.profile_global_contributors():
        counts[global_contributor.count_key] = 0


def _iter_activity_batches(
    activity_ids: list[int], ctx: users_profile_contracts.ProfileExportContext
) -> Iterator[list[activity_schema.ActivityRead]]:
    """Yield the user's activities a page at a time, recording each activity's id.

    Args:
        activity_ids: Receives the id of every activity read, so the caller keeps ids and not rows.
        ctx: The export context.

    Yields:
        One page of activities.
    """
    batch_size = ctx.batch_size
    offset = 0
    while batch := _get_activities_batch(ctx.user_id, offset, batch_size, ctx.db):
        offset += batch_size
        activity_ids.extend(activity.id for activity in batch if activity.id is not None)
        ctx.check_memory(f"activity batch {offset // batch_size}")
        logger.debug(
            "Collected a batch of activities",
            extra=core_logger.context(batch_count=len(batch), total_count=len(activity_ids)),
        )
        yield batch


def _write_global_components(ctx: users_profile_contracts.ProfileExportContext) -> None:
    """Write the file-global activity package records once.

    Args:
        ctx: The export context.
    """
    for contributor in activities_contributor_registry.profile_global_contributors():
        records = contributor.export(ctx.db)
        ctx.archive.write_json(contributor.archive_path, records)
        ctx.counts[contributor.count_key] = len(records)


def _get_activities_batch(user_id: int, offset: int, limit: int, db: Session) -> list[activity_schema.ActivityRead]:
    """Get batch of activities using pagination.

    Args:
        user_id: ID of the user whose activities are read.
        offset: Offset for pagination.
        limit: Number of items per batch.
        db: Database session.

    Returns:
        List of activity objects for the batch.
    """
    # Convert offset to page number (1-based indexing)
    page_number = (offset // limit) + 1

    return activity_integration.list_user_activities_page(
        user_id,
        db,
        page_number=page_number,
        num_records=limit,
    )


def _write_activity_components(ctx: users_profile_contracts.ProfileExportContext, activity_ids: list[int]) -> None:
    """Write the activity-scoped components, a batch of activities at a time.

    Args:
        ctx: The export context.
        activity_ids: IDs of the exported activities.
    """
    # Smaller batches for components
    batch_size = ctx.batch_size // 2

    for contributor in activities_contributor_registry.profile_activity_contributors():
        # Large splittable components are written in chunks during collection
        if contributor.split:
            _write_component_chunked(
                ctx, contributor.count_key, contributor.archive_path, contributor.export, activity_ids, batch_size
            )
        else:
            _write_component_simple(
                ctx, contributor.count_key, contributor.archive_path, contributor.export, activity_ids, batch_size
            )


def _chunk_path(base_filename: str, file_counter: int) -> str:
    """Name one part of a split component entry.

    Args:
        base_filename: Archive path of the unsplit entry.
        file_counter: Index of the part.

    Returns:
        The part's archive path.
    """
    return f"{base_filename.removesuffix('.json')}_{file_counter:03d}.json"


def _write_component_chunked(
    ctx: users_profile_contracts.ProfileExportContext,
    component_key: str,
    base_filename: str,
    export: Callable[[list[int], Session], Sequence[BaseModel]],
    activity_ids: list[int],
    batch_size: int,
) -> None:
    """Write a large component in chunks.

    Args:
        ctx: The export context.
        component_key: Component type identifier.
        base_filename: Base name for output files.
        export: Reads the component's records for some activities.
        activity_ids: List of activity IDs.
        batch_size: Number of items per batch.
    """
    chunk_buffer: list[BaseModel] = []
    file_counter = 0
    max_items_per_file = batch_size
    total_items = 0

    for i in range(0, len(activity_ids), batch_size):
        batch_ids = activity_ids[i : i + batch_size]

        ctx.check_memory(f"{component_key} batch {i // batch_size + 1}")

        data = export(batch_ids, ctx.db)
        if data:
            chunk_buffer.extend(data)
            total_items += len(data)

            # Write chunks to the archive when the buffer reaches max size
            while len(chunk_buffer) >= max_items_per_file:
                chunk_to_write = chunk_buffer[:max_items_per_file]
                chunk_buffer = chunk_buffer[max_items_per_file:]

                ctx.archive.write_json(_chunk_path(base_filename, file_counter), chunk_to_write)
                file_counter += 1

                logger.debug(
                    "Written a chunk of component items",
                    extra=core_logger.context(
                        file_counter=file_counter, component_key=component_key, count=len(chunk_to_write)
                    ),
                )

        logger.debug(
            "Processed a component batch",
            extra=core_logger.context(
                component_key=component_key, batch_number=i // batch_size + 1, count=len(batch_ids)
            ),
        )

    # Write remaining data in buffer
    if chunk_buffer:
        if file_counter == 0:
            # Only one chunk, use original filename
            ctx.archive.write_json(base_filename, chunk_buffer)
            logger.debug(
                "Written component items to a single file",
                extra=core_logger.context(count=len(chunk_buffer), component_key=component_key),
            )
        else:
            # Multiple chunks, write with numbered filename
            ctx.archive.write_json(_chunk_path(base_filename, file_counter), chunk_buffer)
            file_counter += 1
            logger.debug(
                "Written the final chunk of component items",
                extra=core_logger.context(component_key=component_key, count=len(chunk_buffer)),
            )

    if total_items == 0:
        # Write empty file for component type
        ctx.archive.write_json(base_filename, [])
        logger.debug(
            "No component data found, written an empty file", extra=core_logger.context(component_key=component_key)
        )
    else:
        logger.debug(
            "Written component items to files",
            extra=core_logger.context(total_items=total_items, component_key=component_key, file_counter=file_counter),
        )
    ctx.counts[component_key] = total_items


def _write_component_simple(
    ctx: users_profile_contracts.ProfileExportContext,
    component_key: str,
    base_filename: str,
    export: Callable[[list[int], Session], Sequence[BaseModel]],
    activity_ids: list[int],
    batch_size: int,
) -> None:
    """Write a small component as a single file.

    Args:
        ctx: The export context.
        component_key: Component type identifier.
        base_filename: Name for output file.
        export: Reads the component's records for some activities.
        activity_ids: List of activity IDs.
        batch_size: Number of items per batch.
    """
    all_component_data: list[BaseModel] = []

    for i in range(0, len(activity_ids), batch_size):
        batch_ids = activity_ids[i : i + batch_size]

        ctx.check_memory(f"{component_key} batch {i // batch_size + 1}")

        data = export(batch_ids, ctx.db)
        if data:
            all_component_data.extend(data)

        logger.debug(
            "Processed a component batch",
            extra=core_logger.context(
                component_key=component_key, batch_number=i // batch_size + 1, count=len(batch_ids)
            ),
        )

    # An empty list still writes the entry, so the archive names every component
    ctx.archive.write_json(base_filename, all_component_data)
    logger.debug(
        "Written component items to the archive",
        extra=core_logger.context(count=len(all_component_data), component_key=component_key),
    )


def _write_activity_files(ctx: users_profile_contracts.ProfileExportContext, activity_ids: list[int]) -> None:
    """Write each activity's retained source file into the archive.

    Reads the files through the platform ``StorageProvider`` (local disk or object storage) and writes
    each under ``activity_files/{id}{ext}``.

    Args:
        ctx: The export context.
        activity_ids: IDs of the exported activities.
    """
    for activity_id in activity_ids:
        try:
            stored = activity_file_storage_integration.get_activity_file(activity_id, ctx.storage)
            if stored is None:
                continue
            key, data = stored
            ctx.archive.write_bytes(f"{constants.ACTIVITY_FILES_FOLDER}{key}", data)
            ctx.counts["activity_files"] += 1
        except OSError as err:
            logger.warning(
                "Failed to add activity file", exc_info=err, extra=core_logger.context(activity_id=activity_id)
            )
            continue
        except Exception as err:
            logger.warning(
                "Unexpected error adding activity file",
                exc_info=err,
                extra=core_logger.context(activity_id=activity_id),
            )
            continue


def _write_activity_media(ctx: users_profile_contracts.ProfileExportContext, activity_ids: list[int]) -> None:
    """Write each activity's media files into the archive.

    Read through the platform ``StorageProvider`` rather than by walking a local directory, so an
    export is complete regardless of which storage backend is configured. Keys are
    ``{activity_id}_{uuid}{ext}``, so each activity's blobs are listed by its own prefix instead of
    scanning every stored file and filtering.

    Args:
        ctx: The export context.
        activity_ids: IDs of the exported activities.
    """
    for activity_id in activity_ids:
        try:
            blobs = activity_media_integration.list_media_blobs(activity_id, ctx.storage)
        except Exception as err:
            logger.warning(
                "Failed to list media for activity",
                exc_info=err,
                extra=core_logger.context(activity_id=activity_id),
            )
            continue

        for key, data in blobs:
            try:
                ctx.archive.write_bytes(f"{constants.ACTIVITY_MEDIA_FOLDER}{key}", data)
                ctx.counts["media"] += 1
            except Exception as err:
                logger.warning("Unexpected error adding media file", exc_info=err, extra=core_logger.context(key=key))
                continue
