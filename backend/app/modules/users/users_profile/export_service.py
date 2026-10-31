"""Profile data export service for ZIP archive generation.

This module provides the ExportService class for exporting
user profile data including activities, health records, gear,
and settings to a downloadable ZIP archive with streaming.

Key Features:
- Batched data collection for memory efficiency
- Streaming ZIP generation
- Automatic performance tier detection
- Memory and timeout monitoring
"""

import contextlib
import os
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from typing import IO, Any

import jasil.providers as platform_providers
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.contributor_registry as activities_contributor_registry
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.health.health_fasting.integration_service as health_fasting_integration
import modules.health.health_poop.integration_service as health_poop_integration
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.health.health_steps.integration_service as health_steps_integration
import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_water.integration_service as health_water_integration
import modules.health.health_weight.integration_service as health_weight_integration
import modules.users.users.constants as users_constants
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_goals.integration_service as users_goals_integration
import modules.users.users_integrations.constants as user_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_profile.utils as users_profile_utils
from modules.users.users_profile.exceptions import (
    DatabaseConnectionError,
    DataCollectionError,
    ExportTimeoutError,
    FileSystemError,
    MemoryAllocationError,
    ZipCreationError,
)

logger = core_logger.get_logger(__name__)

#: The health record kinds exported beside weight, each with the call that lists a user's records.
_HEALTH_RECORD_LISTERS: dict[str, Callable[[int, Session], list[Any]]] = {
    "health_sleep": health_sleep_integration.list_health_sleep,
    "health_steps": health_steps_integration.list_health_steps,
    "health_water": health_water_integration.list_health_water,
    "health_fasting": health_fasting_integration.list_health_fasting,
    "health_poop": health_poop_integration.list_health_poop,
}


class ExportPerformanceConfig(users_profile_utils.BasePerformanceConfig):
    """Performance configuration for export operations.

    Attributes:
        batch_size: Number of items per batch.
        max_memory_mb: Maximum memory in megabytes.
        compression_level: ZIP compression level.
        chunk_size: Data chunk size in bytes.
        enable_memory_monitoring: Enable memory monitoring.
        timeout_seconds: Operation timeout in seconds.
    """

    def __init__(
        self,
        batch_size: int = 125,
        max_memory_mb: int = 1024,
        compression_level: int = 6,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
        timeout_seconds: int = 3600,
    ):
        """Set the export limits; unset values come from the auto-detected tier."""
        super().__init__(batch_size, max_memory_mb, enable_memory_monitoring, timeout_seconds)
        self.compression_level = compression_level
        self.chunk_size = chunk_size

    @classmethod
    def _get_tier_configs(cls) -> dict[str, dict[str, Any]]:
        """Get tier-specific configuration dictionaries.

        Returns:
            Dictionary mapping tier names to config dicts.
        """
        return {
            "high": {
                "batch_size": 250,
                "max_memory_mb": 2048,
                "compression_level": 6,
                "chunk_size": 16384,
                "timeout_seconds": 7200,
            },
            "medium": {
                "batch_size": 125,
                "max_memory_mb": 1024,
                "compression_level": 6,
                "chunk_size": 8192,
                "timeout_seconds": 3600,
            },
            "low": {
                "batch_size": 50,
                "max_memory_mb": 512,
                "compression_level": 6,
                "chunk_size": 4096,
                "timeout_seconds": 1800,
            },
        }


class ExportService:
    """Service for exporting user profile data to ZIP archive.

    Attributes:
        user_id: ID of user to export data for.
        storage: The platform storage provider.
        db: Database session.
        counts: Dictionary tracking exported item counts.
        performance_config: Performance configuration.
    """

    def __init__(
        self,
        user_id: int,
        storage: platform_providers.StorageProvider,
        db: Session,
        performance_config: ExportPerformanceConfig | None = None,
    ):
        """Bind the export to a user, the platform storage and a database session."""
        self.user_id = user_id
        self.storage = storage
        self.db = db
        self.counts = users_profile_utils.initialize_operation_counts(include_user_count=True)
        self.performance_config: ExportPerformanceConfig = (
            performance_config or ExportPerformanceConfig.get_auto_config()
        )

        logger.debug(
            "ExportService initialized",
            extra=core_logger.context(
                batch_size=self.performance_config.batch_size,
                max_memory_mb=self.performance_config.max_memory_mb,
                compression_level=self.performance_config.compression_level,
                timeout_seconds=self.performance_config.timeout_seconds,
            ),
        )

    def collect_user_activities_data(self, zipf: zipfile.ZipFile) -> list[int]:
        """Stream the user's activities into the ZIP and write their components.

        The activities are read a page at a time and written as they arrive, so no more than one page
        is held, however many the user has. A page that cannot be read fails the export: skipping it
        would leave activities out of an archive that still reports itself complete.

        Args:
            zipf: ZipFile instance to write to.

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
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )
            logger.debug(
                "Starting batched activity collection",
                extra=core_logger.context(batch_size=self.performance_config.batch_size),
            )

            activity_ids: list[int] = []
            users_profile_utils.write_json_array_to_zip(
                zipf, "data/activities.json", self._iter_activity_dicts(activity_ids), self.counts
            )
            logger.debug("Written activities to ZIP", extra=core_logger.context(count=len(activity_ids)))

            if not activity_ids:
                logger.debug("No activities found for the user", extra=core_logger.context(user_id=self.user_id))
            else:
                self._collect_and_write_activity_components(zipf, activity_ids)

            self._collect_and_write_global_activity_components(zipf)

        except SQLAlchemyError as err:
            raise DatabaseConnectionError("Failed to collect activity data") from err
        except MemoryAllocationError as err:
            raise err
        except DataCollectionError:
            raise
        except Exception as err:
            raise DataCollectionError(f"Failed to collect activity data: {err}") from err

        return activity_ids

    def _iter_activity_dicts(self, activity_ids: list[int]) -> Iterator[list[dict[str, Any]]]:
        """Yield the user's activities a page at a time as dicts, recording each activity's id.

        Args:
            activity_ids: Receives the id of every activity read, so the caller keeps ids and not rows.

        Yields:
            One page of serialized activities.
        """
        batch_size = self.performance_config.batch_size
        offset = 0
        while batch := self._get_activities_batch(offset, batch_size):
            offset += batch_size
            activity_ids.extend(activity.id for activity in batch if activity.id is not None)
            users_profile_utils.check_memory_usage(
                f"activity batch {offset // batch_size}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )
            logger.debug(
                "Collected a batch of activities",
                extra=core_logger.context(batch_count=len(batch), total_count=len(activity_ids)),
            )
            yield [users_profile_utils.sqlalchemy_obj_to_dict(activity) for activity in batch]

    def _collect_and_write_global_activity_components(self, zipf: zipfile.ZipFile) -> None:
        """Collect and write file-global activity package records once."""
        for contributor in activities_contributor_registry.profile_global_contributors():
            try:
                records = contributor.export(self.db)
                record_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(record) for record in records]
                users_profile_utils.write_json_to_zip(zipf, contributor.archive_path, record_dicts, self.counts)
                self.counts[contributor.count_key] = len(record_dicts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect {contributor.key}: {err}") from err

    def _get_activities_batch(self, offset: int, limit: int) -> list[Any]:
        """Get batch of activities using pagination.

        Args:
            offset: Offset for pagination.
            limit: Number of items per batch.

        Returns:
            List of activity objects for the batch.
        """
        # Convert offset to page number (1-based indexing)
        page_number = (offset // limit) + 1

        return activity_integration.list_user_activities_page(
            self.user_id,
            self.db,
            page_number=page_number,
            num_records=limit,
        )

    def _collect_and_write_activity_components(
        self,
        zipf: zipfile.ZipFile,
        activity_ids: list[int],
    ) -> None:
        """Collect and write activity components to ZIP.

        Args:
            zipf: ZipFile instance to write to.
            activity_ids: List of activity IDs to process.
        """
        if not activity_ids:
            logger.warning("No activity IDs provided for component collection")
            return
        # Process activity IDs in smaller batches to reduce memory usage
        batch_size = self.performance_config.batch_size // 2  # Smaller batches for components

        for contributor in activities_contributor_registry.profile_activity_contributors():
            # For large splittable components, write in chunks during collection
            if contributor.split:
                self._collect_and_write_component_chunked(
                    zipf,
                    contributor.count_key,
                    contributor.archive_path,
                    contributor.export,
                    activity_ids,
                    batch_size,
                )
            else:
                # For small components, collect all then write
                self._collect_and_write_component_simple(
                    zipf,
                    contributor.count_key,
                    contributor.archive_path,
                    contributor.export,
                    activity_ids,
                    batch_size,
                )

    def _collect_and_write_component_chunked(
        self,
        zipf: zipfile.ZipFile,
        component_key: str,
        base_filename: str,
        crud_func,
        activity_ids: list[int],
        batch_size: int,
    ) -> None:
        """Collect and write large components in chunks.

        Args:
            zipf: ZipFile instance to write to.
            component_key: Component type identifier.
            base_filename: Base name for output files.
            crud_func: CRUD function to fetch data.
            activity_ids: List of activity IDs.
            batch_size: Number of items per batch.
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
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.db)
                if data:
                    # Convert to dicts and add to chunk buffer
                    batch_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(item) for item in data]
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

                        users_profile_utils.write_json_to_zip(zipf, chunk_filename, chunk_to_write, self.counts)
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
                users_profile_utils.write_json_to_zip(zipf, base_filename, chunk_buffer, self.counts)
                logger.debug(
                    "Written component items to a single file",
                    extra=core_logger.context(count=len(chunk_buffer), component_key=component_key),
                )
            else:
                # Multiple chunks, write with numbered filename
                base_name = base_filename.rsplit(".", 1)[0]
                extension = base_filename.rsplit(".", 1)[1] if "." in base_filename else "json"
                chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

                users_profile_utils.write_json_to_zip(zipf, chunk_filename, chunk_buffer, self.counts)
                file_counter += 1
                logger.debug(
                    "Written the final chunk of component items",
                    extra=core_logger.context(component_key=component_key, count=len(chunk_buffer)),
                )

        if total_items == 0:
            # Write empty file for component type
            users_profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            logger.debug(
                "No component data found, written an empty file", extra=core_logger.context(component_key=component_key)
            )
        else:
            logger.debug(
                "Written component items to files",
                extra=core_logger.context(
                    total_items=total_items, component_key=component_key, file_counter=file_counter
                ),
            )
        self.counts[component_key] = total_items

    def _collect_and_write_component_simple(
        self,
        zipf: zipfile.ZipFile,
        component_key: str,
        base_filename: str,
        crud_func,
        activity_ids: list[int],
        batch_size: int,
    ) -> None:
        """Collect and write small components in single file.

        Args:
            zipf: ZipFile instance to write to.
            component_key: Component type identifier.
            base_filename: Name for output file.
            crud_func: CRUD function to fetch data.
            activity_ids: List of activity IDs.
            batch_size: Number of items per batch.
        """
        all_component_data = []

        # Collect component data in batches
        for i in range(0, len(activity_ids), batch_size):
            batch_ids = activity_ids[i : i + batch_size]

            users_profile_utils.check_memory_usage(
                f"{component_key} batch {i // batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.db)
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
            component_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(item) for item in all_component_data]
            users_profile_utils.write_json_to_zip(zipf, base_filename, component_dicts, self.counts)
            logger.debug(
                "Written component items to ZIP",
                extra=core_logger.context(count=len(component_dicts), component_key=component_key),
            )
            # Clear from memory
            all_component_data.clear()
            component_dicts.clear()
        else:
            # Write empty file for component type
            users_profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            logger.debug(
                "No component data found, written an empty file", extra=core_logger.context(component_key=component_key)
            )

    def collect_gear_data(self, zipf: zipfile.ZipFile) -> None:
        """Collect and write gear data to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write gears
            try:
                gears = gear_integration.get_gear_user(self.user_id, self.db)
                if gears:
                    gears_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(g) for g in gears]
                    users_profile_utils.write_json_to_zip(zipf, "data/gears.json", gears_dicts, self.counts)
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/gears.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect gears: {err}") from err

            # Collect and write gear components
            try:
                gear_components = gear_components_integration.get_gear_components_user(self.user_id, self.db)
                if gear_components:
                    gear_components_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(gc) for gc in gear_components]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/gear_components.json",
                        gear_components_dicts,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/gear_components.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect gear components: {err}") from err

        except SQLAlchemyError as err:
            raise DatabaseConnectionError("Failed to collect gear data") from err

    def collect_health_weight(self, zipf: zipfile.ZipFile) -> None:
        """Collect and write health data to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write health data
            try:
                health_weight = health_weight_integration.list_health_weight(self.user_id, self.db)
                if health_weight:
                    health_weight_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(hd) for hd in health_weight]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/health_weight.json",
                        health_weight_dicts,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/health_weight.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect health data: {err}") from err

            # Collect and write health targets
            try:
                health_targets = health_targets_integration.get_health_targets(self.user_id, self.db)
                if health_targets:
                    # health_targets is a single object, not a list
                    health_targets_dict = users_profile_utils.sqlalchemy_obj_to_dict(health_targets)
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/health_targets.json",
                        [health_targets_dict],
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/health_targets.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect health targets: {err}") from err

        except SQLAlchemyError as err:
            raise DatabaseConnectionError("Failed to collect health data") from err

    def collect_health_records(self, zipf: zipfile.ZipFile) -> None:
        """Collect and write sleep, steps, water, fasting and poop records to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DataCollectionError: If a kind of record cannot be collected.
            DatabaseConnectionError: If database error occurs.
        """
        try:
            for name, list_records in _HEALTH_RECORD_LISTERS.items():
                try:
                    records = [
                        users_profile_utils.sqlalchemy_obj_to_dict(r) for r in list_records(self.user_id, self.db)
                    ]
                except SQLAlchemyError:
                    raise
                except Exception as err:
                    raise DataCollectionError(f"Failed to collect {name}: {err}") from err
                users_profile_utils.write_json_to_zip(zipf, f"data/{name}.json", records, self.counts)
        except SQLAlchemyError as err:
            raise DatabaseConnectionError("Failed to collect health records") from err

    def collect_user_settings_data(self, zipf: zipfile.ZipFile) -> None:
        """Collect and write user settings to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write user default gear
            try:
                user_default_gear: user_default_gear_schema.UsersDefaultGearRead | None = (
                    users_default_gear_integration.get_default_gear(self.user_id, self.db)
                )
                if user_default_gear:
                    default_gear_dict = [user_default_gear.model_dump(mode="json")]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_default_gear.json",
                        default_gear_dict,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_default_gear.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect user default gear: {err}") from err

            # Collect and write user goals
            try:
                user_goals = users_goals_integration.list_goals(self.user_id, self.db)
                if user_goals:
                    user_goals_dicts = [ug.model_dump() for ug in user_goals]
                    users_profile_utils.write_json_to_zip(zipf, "data/user_goals.json", user_goals_dicts, self.counts)
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_goals.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect user goals: {err}") from err

            # Collect and write user integrations
            try:
                user_integrations = user_integrations_integration.get_user_integrations(self.user_id, self.db)
                if user_integrations:
                    integrations_dict = [
                        {
                            field: getattr(user_integrations, field)
                            for field in user_integrations_constants.PORTABLE_INTEGRATION_FIELDS
                        }
                    ]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_integrations.json",
                        integrations_dict,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_integrations.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect user integrations: {err}") from err

            # Collect and write user privacy settings
            try:
                user_privacy_settings = users_privacy_settings_integration.get_privacy_settings(self.user_id, self.db)
                if user_privacy_settings:
                    privacy_dict = [users_profile_utils.sqlalchemy_obj_to_dict(user_privacy_settings)]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_privacy_settings.json",
                        privacy_dict,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_privacy_settings.json", [], self.counts)
            except Exception as err:
                raise DataCollectionError(f"Failed to collect user privacy settings: {err}") from err

        except SQLAlchemyError as err:
            raise DatabaseConnectionError("Failed to collect user settings") from err

    def add_activity_files_to_zip(self, zipf: zipfile.ZipFile, activity_ids: list[int]):
        """Add activity files to ZIP archive.

        Reads each activity's retained source file through the platform
        ``StorageProvider`` (local disk or object storage) and writes it into the
        archive under ``activity_files/{id}{ext}``.

        Args:
            zipf: ZipFile instance to write to.
            activity_ids: IDs of the exported activities.
        """
        if not activity_ids:
            return

        storage = self.storage
        for activity_id in activity_ids:
            try:
                stored = activity_file_storage_integration.get_activity_file(activity_id, storage)
                if stored is None:
                    continue
                key, data = stored
                zipf.writestr(os.path.join("activity_files", key), data)
                self.counts["activity_files"] += 1
            except MemoryAllocationError:
                raise
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

    def add_activity_media_to_zip(self, zipf: zipfile.ZipFile, activity_ids: list[int]):
        """Add activity media files to ZIP archive.

        Read through the platform ``StorageProvider`` rather than by walking a
        local directory, so an export is complete regardless of which storage
        backend is configured. Keys are ``{activity_id}_{uuid}{ext}``, so each
        activity's blobs are listed by its own prefix instead of scanning every
        stored file and filtering.

        Args:
            zipf: ZipFile instance to write to.
            activity_ids: IDs of the exported activities.
        """
        if not activity_ids:
            return

        storage = self.storage

        for activity_id in activity_ids:
            try:
                blobs = activity_media_integration.list_media_blobs(activity_id, storage)
            except Exception as err:
                logger.warning(
                    "Failed to list media for activity",
                    exc_info=err,
                    extra=core_logger.context(activity_id=activity_id),
                )
                continue

            for key, data in blobs:
                try:
                    zipf.writestr(os.path.join("activity_media", key), data)
                    self.counts["media"] += 1
                except MemoryAllocationError:
                    raise
                except Exception as err:
                    logger.warning(
                        "Unexpected error adding media file", exc_info=err, extra=core_logger.context(key=key)
                    )
                    continue

    def add_user_images_to_zip(self, zipf: zipfile.ZipFile):
        """Add the user's profile image to the ZIP archive.

        Read through the platform ``StorageProvider`` rather than by walking a
        local directory, so an export is complete regardless of which storage
        backend is configured. Keys are ``{user_id}{ext}``, so the caller's
        blobs are listed by their own prefix instead of scanning every stored
        image and filtering by filename.

        Args:
            zipf: ZipFile instance to write to.
        """
        storage = self.storage
        area = users_constants.USER_IMAGE_STORAGE_AREA

        try:
            keys = storage.list_keys(area, f"{self.user_id}.")
        except Exception as err:
            logger.warning("Failed to list user images", exc_info=err, extra=core_logger.context(user_id=self.user_id))
            return

        for key in keys:
            try:
                data = storage.get(area, key)
                if data is None:
                    logger.warning("User image blob not found", extra=core_logger.context(key=key))
                    continue

                size = len(data)
                if size > 10 * 1024 * 1024:
                    logger.warning(
                        "Large user image file", extra=core_logger.context(key=key, size_mb=size / (1024 * 1024))
                    )
                if size > 5 * 1024 * 1024:
                    users_profile_utils.check_memory_usage(
                        f"before image {key}",
                        self.performance_config.max_memory_mb,
                        self.performance_config.enable_memory_monitoring,
                    )

                zipf.writestr(os.path.join("user_images", key), data)
                self.counts["user_images"] += 1
            except MemoryAllocationError:
                raise
            except Exception as err:
                logger.warning("Unexpected error adding user image", exc_info=err, extra=core_logger.context(key=key))

    def build_export_archive(self, user_dict: dict[str, Any], timeout_seconds: int | None = 300) -> IO[bytes]:
        """Build the export ZIP in a temporary file and return it, rewound to the start.

        Everything that can fail (database reads, storage reads, the timeout) happens here, before
        any response bytes exist, so a failure becomes an error response instead of a truncated
        download. The caller owns the returned file and must close it, which deletes it.

        Args:
            user_dict: User data dictionary to export.
            timeout_seconds: Optional timeout in seconds for building the archive.

        Returns:
            The finished archive, positioned at its first byte.

        Raises:
            ExportTimeoutError: If operation times out.
            ZipCreationError: If ZIP creation fails.
            MemoryAllocationError: If memory limit exceeded.
            FileSystemError: If file system error occurs.
        """
        start_time = time.time()
        with contextlib.ExitStack() as stack:
            archive = stack.enter_context(tempfile.TemporaryFile())
            self._write_archive(archive, user_dict, timeout_seconds, start_time)
            archive.flush()
            size = archive.tell()
            archive.seek(0)
            logger.debug("ZIP archive created successfully", extra=core_logger.context(size_mb=size / (1024 * 1024)))
            # Built without error: ownership passes to the caller, so the stack must not close it.
            stack.pop_all()

        return archive

    def _write_archive(
        self, archive: IO[bytes], user_dict: dict[str, Any], timeout_seconds: int | None, start_time: float
    ) -> None:
        """Write the export ZIP into an open file, mapping low-level failures to export errors.

        Args:
            archive: The file the ZIP is written to.
            user_dict: User data dictionary to export.
            timeout_seconds: Optional timeout in seconds.
            start_time: When the export began, for the timeout.

        Raises:
            ExportTimeoutError: If operation times out.
            ZipCreationError: If ZIP creation fails.
            MemoryAllocationError: If memory limit exceeded.
            FileSystemError: If file system error occurs.
        """
        try:
            compression_level = self.performance_config.compression_level
            logger.debug("Creating ZIP", extra=core_logger.context(compression_level=compression_level))

            with zipfile.ZipFile(
                archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=compression_level,
            ) as zipf:
                logger.debug("Starting export", extra=core_logger.context(user_id=self.user_id))

                # Database phase first: activities, gear, health and settings.
                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                activity_ids = self.collect_user_activities_data(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.collect_gear_data(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.collect_health_weight(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.collect_health_records(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.collect_user_settings_data(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                users_profile_utils.write_json_to_zip(zipf, "data/user.json", [user_dict], self.counts)

                # Everything below reads object storage only, which can take a long time, so the
                # read transaction ends here instead of pinning a pool connection throughout.
                self.db.commit()

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.add_activity_files_to_zip(zipf, activity_ids)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.add_activity_media_to_zip(zipf, activity_ids)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.add_user_images_to_zip(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                users_profile_utils.write_json_to_zip(zipf, "counts.json", [self.counts], self.counts)

                logger.debug("Export completed successfully", extra=core_logger.context(counts=self.counts))

        except zipfile.BadZipFile as err:
            raise ZipCreationError(f"Failed to create ZIP archive: {err}") from err
        except zipfile.LargeZipFile as err:
            raise ZipCreationError(f"Export archive too large: {err}") from err
        except OSError as err:
            raise FileSystemError(f"File system error during export: {err}") from err
        except MemoryError as err:
            raise MemoryAllocationError(f"Insufficient memory for export: {err}") from err
