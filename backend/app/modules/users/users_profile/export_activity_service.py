"""Activity collection for the profile data export.

Streams the user's activities and their components (laps, sets, streams, workout steps, media
records, file-global records) into the export ZIP a page or batch at a time, so memory stays
bounded however many activities the user has.
"""

import zipfile
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.contributor_registry as activities_contributor_registry
import modules.users.users_profile.utils as users_profile_utils
from modules.users.users_profile.exceptions import (
    DatabaseConnectionError,
    DataCollectionError,
    MemoryAllocationError,
)

logger = core_logger.get_logger(__name__)


def collect_user_activities_data(
    zipf: zipfile.ZipFile,
    user_id: int,
    counts: dict[str, int],
    performance_config: users_profile_utils.BasePerformanceConfig,
    db: Session,
) -> list[int]:
    """Stream the user's activities into the ZIP and write their components.

    The activities are read a page at a time and written as they arrive, so no more than one page
    is held, however many the user has. A page that cannot be read fails the export: skipping it
    would leave activities out of an archive that still reports itself complete.

    Args:
        zipf: ZipFile instance to write to.
        user_id: ID of the user whose activities are exported.
        counts: Exported item counts, updated as items are written.
        performance_config: Batch size and memory limits.
        db: Database session.

    Returns:
        The ids of the exported activities, which the later steps read their files and media by.

    Raises:
        DatabaseConnectionError: If database error occurs.
        MemoryAllocationError: If memory limit exceeded.
        DataCollectionError: If collection fails.
    """
    try:
        users_profile_utils.check_memory_usage(
            "activity collection start",
            performance_config.max_memory_mb,
            performance_config.enable_memory_monitoring,
        )
        logger.debug(
            "Starting batched activity collection",
            extra=core_logger.context(batch_size=performance_config.batch_size),
        )

        activity_ids: list[int] = []
        users_profile_utils.write_json_array_to_zip(
            zipf, "data/activities.json", _iter_activity_dicts(activity_ids, user_id, performance_config, db), counts
        )
        logger.debug("Written activities to ZIP", extra=core_logger.context(count=len(activity_ids)))

        if not activity_ids:
            logger.debug("No activities found for the user", extra=core_logger.context(user_id=user_id))
        else:
            _collect_and_write_activity_components(zipf, activity_ids, counts, performance_config, db)

        _collect_and_write_global_activity_components(zipf, counts, db)

    except SQLAlchemyError as err:
        raise DatabaseConnectionError("Failed to collect activity data") from err
    except MemoryAllocationError as err:
        raise err
    except DataCollectionError:
        raise
    except Exception as err:
        raise DataCollectionError(f"Failed to collect activity data: {err}") from err

    return activity_ids


def _iter_activity_dicts(
    activity_ids: list[int],
    user_id: int,
    performance_config: users_profile_utils.BasePerformanceConfig,
    db: Session,
) -> Iterator[list[dict[str, Any]]]:
    """Yield the user's activities a page at a time as dicts, recording each activity's id.

    Args:
        activity_ids: Receives the id of every activity read, so the caller keeps ids and not rows.
        user_id: ID of the user whose activities are read.
        performance_config: Batch size and memory limits.
        db: Database session.

    Yields:
        One page of serialized activities.
    """
    batch_size = performance_config.batch_size
    offset = 0
    while batch := _get_activities_batch(user_id, offset, batch_size, db):
        offset += batch_size
        activity_ids.extend(activity.id for activity in batch if activity.id is not None)
        users_profile_utils.check_memory_usage(
            f"activity batch {offset // batch_size}",
            performance_config.max_memory_mb,
            performance_config.enable_memory_monitoring,
        )
        logger.debug(
            "Collected a batch of activities",
            extra=core_logger.context(batch_count=len(batch), total_count=len(activity_ids)),
        )
        yield [users_profile_utils.model_to_dict(activity) for activity in batch]


def _collect_and_write_global_activity_components(zipf: zipfile.ZipFile, counts: dict[str, int], db: Session) -> None:
    """Collect and write file-global activity package records once.

    Args:
        zipf: ZipFile instance to write to.
        counts: Exported item counts, updated as items are written.
        db: Database session.
    """
    for contributor in activities_contributor_registry.profile_global_contributors():
        try:
            records = contributor.export(db)
            record_dicts = [users_profile_utils.model_to_dict(record) for record in records]
            users_profile_utils.write_json_to_zip(zipf, contributor.archive_path, record_dicts, counts)
            counts[contributor.count_key] = len(record_dicts)
        except Exception as err:
            raise DataCollectionError(f"Failed to collect {contributor.key}: {err}") from err


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


def _collect_and_write_activity_components(
    zipf: zipfile.ZipFile,
    activity_ids: list[int],
    counts: dict[str, int],
    performance_config: users_profile_utils.BasePerformanceConfig,
    db: Session,
) -> None:
    """Collect and write activity components to ZIP.

    Args:
        zipf: ZipFile instance to write to.
        activity_ids: List of activity IDs to process.
        counts: Exported item counts, updated as items are written.
        performance_config: Batch size and memory limits.
        db: Database session.
    """
    if not activity_ids:
        logger.warning("No activity IDs provided for component collection")
        return
    # Process activity IDs in smaller batches to reduce memory usage
    batch_size = performance_config.batch_size // 2  # Smaller batches for components

    for contributor in activities_contributor_registry.profile_activity_contributors():
        # For large splittable components, write in chunks during collection
        if contributor.split:
            _collect_and_write_component_chunked(
                zipf,
                contributor.count_key,
                contributor.archive_path,
                contributor.export,
                activity_ids,
                batch_size,
                counts,
                performance_config,
                db,
            )
        else:
            # For small components, collect all then write
            _collect_and_write_component_simple(
                zipf,
                contributor.count_key,
                contributor.archive_path,
                contributor.export,
                activity_ids,
                batch_size,
                counts,
                performance_config,
                db,
            )


def _collect_and_write_component_chunked(
    zipf: zipfile.ZipFile,
    component_key: str,
    base_filename: str,
    crud_func: Callable[[list[int], Session], Sequence[BaseModel]],
    activity_ids: list[int],
    batch_size: int,
    counts: dict[str, int],
    performance_config: users_profile_utils.BasePerformanceConfig,
    db: Session,
) -> None:
    """Collect and write large components in chunks.

    Args:
        zipf: ZipFile instance to write to.
        component_key: Component type identifier.
        base_filename: Base name for output files.
        crud_func: CRUD function to fetch data.
        activity_ids: List of activity IDs.
        batch_size: Number of items per batch.
        counts: Exported item counts, updated as items are written.
        performance_config: Memory limits.
        db: Database session.
    """
    chunk_buffer = []
    file_counter = 0
    max_items_per_file = batch_size
    total_items = 0

    # Collect component data in batches
    for i in range(0, len(activity_ids), batch_size):
        batch_ids = activity_ids[i : i + batch_size]

        users_profile_utils.check_memory_usage(
            f"{component_key} batch {i // batch_size + 1}",
            performance_config.max_memory_mb,
            performance_config.enable_memory_monitoring,
        )

        try:
            data = crud_func(batch_ids, db)
            if data:
                # Convert to dicts and add to chunk buffer
                batch_dicts = [users_profile_utils.model_to_dict(item) for item in data]
                chunk_buffer.extend(batch_dicts)
                total_items += len(batch_dicts)

                # Write chunks to ZIP when buffer reaches max size
                while len(chunk_buffer) >= max_items_per_file:
                    chunk_to_write = chunk_buffer[:max_items_per_file]
                    chunk_buffer = chunk_buffer[max_items_per_file:]

                    # Generate filename for this chunk
                    base_name = base_filename.rsplit(".", 1)[0]
                    extension = base_filename.rsplit(".", 1)[1] if "." in base_filename else "json"
                    chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

                    users_profile_utils.write_json_to_zip(zipf, chunk_filename, chunk_to_write, counts)
                    file_counter += 1

                    logger.debug(
                        "Written a chunk of component items",
                        extra=core_logger.context(
                            file_counter=file_counter, component_key=component_key, count=len(chunk_to_write)
                        ),
                    )

        except Exception as err:
            raise DataCollectionError(f"Failed to collect {component_key}: {err}") from err

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
            users_profile_utils.write_json_to_zip(zipf, base_filename, chunk_buffer, counts)
            logger.debug(
                "Written component items to a single file",
                extra=core_logger.context(count=len(chunk_buffer), component_key=component_key),
            )
        else:
            # Multiple chunks, write with numbered filename
            base_name = base_filename.rsplit(".", 1)[0]
            extension = base_filename.rsplit(".", 1)[1] if "." in base_filename else "json"
            chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

            users_profile_utils.write_json_to_zip(zipf, chunk_filename, chunk_buffer, counts)
            file_counter += 1
            logger.debug(
                "Written the final chunk of component items",
                extra=core_logger.context(component_key=component_key, count=len(chunk_buffer)),
            )

    if total_items == 0:
        # Write empty file for component type
        users_profile_utils.write_json_to_zip(zipf, base_filename, [], counts)
        logger.debug(
            "No component data found, written an empty file", extra=core_logger.context(component_key=component_key)
        )
    else:
        logger.debug(
            "Written component items to files",
            extra=core_logger.context(total_items=total_items, component_key=component_key, file_counter=file_counter),
        )
    counts[component_key] = total_items


def _collect_and_write_component_simple(
    zipf: zipfile.ZipFile,
    component_key: str,
    base_filename: str,
    crud_func: Callable[[list[int], Session], Sequence[BaseModel]],
    activity_ids: list[int],
    batch_size: int,
    counts: dict[str, int],
    performance_config: users_profile_utils.BasePerformanceConfig,
    db: Session,
) -> None:
    """Collect and write small components in single file.

    Args:
        zipf: ZipFile instance to write to.
        component_key: Component type identifier.
        base_filename: Name for output file.
        crud_func: CRUD function to fetch data.
        activity_ids: List of activity IDs.
        batch_size: Number of items per batch.
        counts: Exported item counts, updated as items are written.
        performance_config: Memory limits.
        db: Database session.
    """
    all_component_data: list[BaseModel] = []

    # Collect component data in batches
    for i in range(0, len(activity_ids), batch_size):
        batch_ids = activity_ids[i : i + batch_size]

        users_profile_utils.check_memory_usage(
            f"{component_key} batch {i // batch_size + 1}",
            performance_config.max_memory_mb,
            performance_config.enable_memory_monitoring,
        )

        try:
            data = crud_func(batch_ids, db)
            if data:
                all_component_data.extend(data)
        except Exception as err:
            raise DataCollectionError(f"Failed to collect {component_key}: {err}") from err

        logger.debug(
            "Processed a component batch",
            extra=core_logger.context(
                component_key=component_key, batch_number=i // batch_size + 1, count=len(batch_ids)
            ),
        )

    # Write all component data to ZIP
    if all_component_data:
        component_dicts = [users_profile_utils.model_to_dict(item) for item in all_component_data]
        users_profile_utils.write_json_to_zip(zipf, base_filename, component_dicts, counts)
        logger.debug(
            "Written component items to ZIP",
            extra=core_logger.context(count=len(component_dicts), component_key=component_key),
        )
        # Clear from memory
        all_component_data.clear()
        component_dicts.clear()
    else:
        # Write empty file for component type
        users_profile_utils.write_json_to_zip(zipf, base_filename, [], counts)
        logger.debug(
            "No component data found, written an empty file", extra=core_logger.context(component_key=component_key)
        )
