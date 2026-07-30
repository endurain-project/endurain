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

import os
import tempfile
import time
import zipfile
from collections.abc import Generator
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.integration_service as activities_integration
import modules.activities.activity_file_storage.service as activity_file_storage_service
import modules.activities.activity_media.signing as activity_media_signing
import modules.gears.gear.crud as gear_crud
import modules.gears.gear_components.crud as gear_components_crud
import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_weight.crud as health_weight_crud
import modules.users.users.signing as users_signing
import modules.users.users_default_gear.crud as user_default_gear_crud
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_goals.crud as user_goals_crud
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
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


class ExportPerformanceConfig(users_profile_utils.BasePerformanceConfig):
    """
    Performance configuration for export operations.

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
        super().__init__(batch_size, max_memory_mb, enable_memory_monitoring, timeout_seconds)
        self.compression_level = compression_level
        self.chunk_size = chunk_size

    @classmethod
    def _get_tier_configs(cls) -> dict[str, dict[str, Any]]:
        """
        Get tier-specific configuration dictionaries.

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
    """
    Service for exporting user profile data to ZIP archive.

    Attributes:
        user_id: ID of user to export data for.
        db: Database session.
        counts: Dictionary tracking exported item counts.
        performance_config: Performance configuration.
    """

    def __init__(
        self,
        user_id: int,
        db: Session,
        performance_config: ExportPerformanceConfig | None = None,
    ):
        self.user_id = user_id
        self.db = db
        self.counts = users_profile_utils.initialize_operation_counts(include_user_count=True)
        self.performance_config: ExportPerformanceConfig = (
            performance_config or ExportPerformanceConfig.get_auto_config()
        )

        logger.info(
            f"ExportService initialized with performance config: "
            f"batch_size={self.performance_config.batch_size}, "
            f"max_memory_mb={self.performance_config.max_memory_mb}, "
            f"compression_level={self.performance_config.compression_level}, "
            f"timeout_seconds={self.performance_config.timeout_seconds}"
        )

    def collect_user_activities_data(self, zipf: zipfile.ZipFile) -> list[Any]:
        """
        Collect and write user activities to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Returns:
            List of collected activity objects.

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

            # Get activities in batches using pagination
            all_activities = []
            offset = 0
            batch_size = self.performance_config.batch_size

            logger.info(f"Starting batched activity collection with batch_size={batch_size}")

            while True:
                # Get a batch of activities
                try:
                    batch_activities = self._get_activities_batch(offset, batch_size)
                except (SQLAlchemyError, MemoryAllocationError):
                    # Persistent failures must propagate so the outer handlers can
                    # return an explicit error rather than silently skipping pages.
                    raise
                except Exception as err:
                    logger.warning(f"Failed to get activities batch (offset={offset}), skipping: {err}", exc_info=err)
                    offset += batch_size
                    continue

                if not batch_activities:
                    break

                all_activities.extend(batch_activities)
                offset += batch_size

                # Check memory usage after each batch
                users_profile_utils.check_memory_usage(
                    f"activity batch {offset // batch_size}",
                    self.performance_config.max_memory_mb,
                    self.performance_config.enable_memory_monitoring,
                )

                logger.info(f"Collected {len(batch_activities)} activities in batch (total: {len(all_activities)})")

            if not all_activities:
                logger.info(f"No activities found for user {self.user_id}")
                # Write empty activities file
                users_profile_utils.write_json_to_zip(zipf, "data/activities.json", [], self.counts)
                return []

            # Write activities to ZIP immediately
            activities_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(a) for a in all_activities]
            users_profile_utils.write_json_to_zip(zipf, "data/activities.json", activities_dicts, self.counts)

            logger.info(f"Written {len(activities_dicts)} activities to ZIP")

            # Filter out activities with None IDs and collect valid IDs
            activity_ids = [activity.id for activity in all_activities if activity.id is not None]

            if not activity_ids:
                logger.warning(f"No valid activity IDs found for user {self.user_id}")
                return all_activities

            # Collect and write activity components progressively
            self._collect_and_write_activity_components(zipf, activity_ids, all_activities)

            # Exercise titles don't depend on activity IDs
            try:
                exercise_titles = activities_integration.list_exercise_titles(self.db)
                if exercise_titles:
                    exercise_titles_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(e) for e in exercise_titles]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/activity_exercise_titles.json",
                        exercise_titles_dicts,
                        self.counts,
                    )
            except Exception as err:
                logger.error(f"Failed to collect exercise titles: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect exercise titles: {err}") from err

        except SQLAlchemyError as err:
            logger.error(f"Database error collecting activities: {err}", exc_info=err)
            raise DatabaseConnectionError(f"Failed to collect activity data: {err}") from err
        except MemoryAllocationError as err:
            logger.error(f"Memory limit exceeded while collecting activities: {err}. ", exc_info=err)
            raise err
        except DataCollectionError:
            raise
        except Exception as err:
            logger.error(f"Unexpected error collecting activities: {err}", exc_info=err)
            raise DataCollectionError(f"Failed to collect activity data: {err}") from err

        return all_activities

    def _get_activities_batch(self, offset: int, limit: int) -> list[Any]:
        """
        Get batch of activities using pagination.

        Args:
            offset: Offset for pagination.
            limit: Number of items per batch.

        Returns:
            List of activity objects for the batch.
        """
        try:
            # Convert offset to page number (1-based indexing)
            page_number = (offset // limit) + 1

            return activities_integration.list_user_activities_page(
                self.user_id,
                page_number,
                limit,
                self.db,
            )

        except Exception as err:
            logger.error(f"Failed to get activities batch (offset={offset}, limit={limit}): {err}", exc_info=err)
            raise

    def _collect_and_write_activity_components(
        self,
        zipf: zipfile.ZipFile,
        activity_ids: list[int],
        user_activities: list[Any],
    ) -> None:
        """
        Collect and write activity components to ZIP.

        Args:
            zipf: ZipFile instance to write to.
            activity_ids: List of activity IDs to process.
            user_activities: List of activity objects.
        """
        if not activity_ids or not user_activities:
            logger.warning("No activity IDs or activities provided for component collection")
            return
        # Process activity IDs in smaller batches to reduce memory usage
        batch_size = self.performance_config.batch_size // 2  # Smaller batches for components

        # Component definitions: (key, filename, crud_function, should_split)
        component_types = [
            (
                "laps",
                "data/activity_laps.json",
                activities_integration.list_activities_laps,
                True,
            ),
            (
                "sets",
                "data/activity_sets.json",
                activities_integration.list_activities_sets,
                True,
            ),
            (
                "streams",
                "data/activity_streams.json",
                activities_integration.list_activities_streams,
                True,
            ),
            (
                "steps",
                "data/activity_workout_steps.json",
                activities_integration.list_activities_workout_steps,
                False,
            ),
            (
                "media",
                "data/activity_media.json",
                activities_integration.list_activities_media,
                False,
            ),
        ]

        for component_key, base_filename, crud_func, should_split in component_types:
            # For large splittable components, write in chunks during collection
            if should_split:
                self._collect_and_write_component_chunked(
                    zipf,
                    component_key,
                    base_filename,
                    crud_func,
                    activity_ids,
                    user_activities,
                    batch_size,
                )
            else:
                # For small components, collect all then write
                self._collect_and_write_component_simple(
                    zipf,
                    component_key,
                    base_filename,
                    crud_func,
                    activity_ids,
                    user_activities,
                    batch_size,
                )

    def _collect_and_write_component_chunked(
        self,
        zipf: zipfile.ZipFile,
        component_key: str,
        base_filename: str,
        crud_func,
        activity_ids: list[int],
        user_activities: list[Any],
        batch_size: int,
    ) -> None:
        """
        Collect and write large components in chunks.

        Args:
            zipf: ZipFile instance to write to.
            component_key: Component type identifier.
            base_filename: Base name for output files.
            crud_func: CRUD function to fetch data.
            activity_ids: List of activity IDs.
            user_activities: List of activity objects.
            batch_size: Number of items per batch.
        """
        chunk_buffer = []
        file_counter = 0
        max_items_per_file = batch_size
        total_items = 0

        # Collect component data in batches
        for i in range(0, len(activity_ids), batch_size):
            batch_ids = activity_ids[i : i + batch_size]
            batch_activities = user_activities[i : i + batch_size]

            users_profile_utils.check_memory_usage(
                f"{component_key} batch {i // batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.user_id, self.db, batch_activities)
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

                        logger.debug(f"Written chunk {file_counter} for {component_key} ({len(chunk_to_write)} items)")

            except Exception as err:
                logger.error(f"Failed to collect batch for {component_key}: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect {component_key}: {err}") from err

            logger.info(f"Processed {component_key} batch {i // batch_size + 1} ({len(batch_ids)} activities)")

        # Write remaining data in buffer
        if chunk_buffer:
            if file_counter == 0:
                # Only one chunk, use original filename
                users_profile_utils.write_json_to_zip(zipf, base_filename, chunk_buffer, self.counts)
                logger.info(f"Written {len(chunk_buffer)} {component_key} items to single file")
            else:
                # Multiple chunks, write with numbered filename
                base_name = base_filename.rsplit(".", 1)[0]
                extension = base_filename.rsplit(".", 1)[1] if "." in base_filename else "json"
                chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

                users_profile_utils.write_json_to_zip(zipf, chunk_filename, chunk_buffer, self.counts)
                file_counter += 1
                logger.debug(f"Written final chunk for {component_key} ({len(chunk_buffer)} items)")

        if total_items == 0:
            # Write empty file for component type
            users_profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            logger.info(f"No {component_key} data found, written empty file")
        else:
            logger.info(f"Written total {total_items} {component_key} items to {file_counter} file(s)")

    def _collect_and_write_component_simple(
        self,
        zipf: zipfile.ZipFile,
        component_key: str,
        base_filename: str,
        crud_func,
        activity_ids: list[int],
        user_activities: list[Any],
        batch_size: int,
    ) -> None:
        """
        Collect and write small components in single file.

        Args:
            zipf: ZipFile instance to write to.
            component_key: Component type identifier.
            base_filename: Name for output file.
            crud_func: CRUD function to fetch data.
            activity_ids: List of activity IDs.
            user_activities: List of activity objects.
            batch_size: Number of items per batch.
        """
        all_component_data = []

        # Collect component data in batches
        for i in range(0, len(activity_ids), batch_size):
            batch_ids = activity_ids[i : i + batch_size]
            batch_activities = user_activities[i : i + batch_size]

            users_profile_utils.check_memory_usage(
                f"{component_key} batch {i // batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.user_id, self.db, batch_activities)
                if data:
                    all_component_data.extend(data)
            except Exception as err:
                logger.error(f"Failed to collect batch for {component_key}: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect {component_key}: {err}") from err

            logger.info(f"Processed {component_key} batch {i // batch_size + 1} ({len(batch_ids)} activities)")

        # Write all component data to ZIP
        if all_component_data:
            component_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(item) for item in all_component_data]
            users_profile_utils.write_json_to_zip(zipf, base_filename, component_dicts, self.counts)
            logger.info(f"Written {len(component_dicts)} {component_key} items to ZIP")
            # Clear from memory
            all_component_data.clear()
            component_dicts.clear()
        else:
            # Write empty file for component type
            users_profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            logger.info(f"No {component_key} data found, written empty file")

    def collect_gear_data(self, zipf: zipfile.ZipFile) -> None:
        """
        Collect and write gear data to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write gears
            try:
                gears = gear_crud.get_gear_user(self.user_id, self.db)
                if gears:
                    gears_dicts = [users_profile_utils.sqlalchemy_obj_to_dict(g) for g in gears]
                    users_profile_utils.write_json_to_zip(zipf, "data/gears.json", gears_dicts, self.counts)
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/gears.json", [], self.counts)
            except Exception as err:
                logger.error(f"Failed to collect gears: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect gears: {err}") from err

            # Collect and write gear components
            try:
                gear_components = gear_components_crud.get_gear_components_user(self.user_id, self.db)
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
                logger.error(f"Failed to collect gear components: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect gear components: {err}") from err

        except SQLAlchemyError as err:
            logger.error(f"Database error collecting gear data: {err}", exc_info=err)
            raise DatabaseConnectionError(f"Failed to collect gear data: {err}") from err

    def collect_health_weight(self, zipf: zipfile.ZipFile) -> None:
        """
        Collect and write health data to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write health data
            try:
                health_weight = health_weight_crud.get_all_health_weight_by_user_id(self.user_id, self.db)
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
                logger.error(f"Failed to collect health data: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect health data: {err}") from err

            # Collect and write health targets
            try:
                health_targets = health_targets_crud.get_health_targets_by_user_id(self.user_id, self.db)
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
                logger.error(f"Failed to collect health targets: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect health targets: {err}") from err

        except SQLAlchemyError as err:
            logger.error(f"Database error collecting health data: {err}", exc_info=err)
            raise DatabaseConnectionError(f"Failed to collect health data: {err}") from err

    def collect_user_settings_data(self, zipf: zipfile.ZipFile) -> None:
        """
        Collect and write user settings to ZIP.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            DatabaseConnectionError: If database error occurs.
        """
        try:
            # Collect and write user default gear
            try:
                user_default_gear: user_default_gear_schema.UsersDefaultGearRead | None = (
                    user_default_gear_crud.get_user_default_gear_by_user_id(self.user_id, self.db)
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
                logger.error(f"Failed to collect user default gear: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect user default gear: {err}") from err

            # Collect and write user goals
            try:
                user_goals = user_goals_crud.get_user_goals_by_user_id(self.user_id, self.db)
                if user_goals:
                    user_goals_dicts = [ug.model_dump() for ug in user_goals]
                    users_profile_utils.write_json_to_zip(zipf, "data/user_goals.json", user_goals_dicts, self.counts)
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_goals.json", [], self.counts)
            except Exception as err:
                logger.error(f"Failed to collect user goals: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect user goals: {err}") from err

            # Collect and write user integrations
            try:
                user_integrations = user_integrations_crud.get_user_integrations_by_user_id(self.user_id, self.db)
                if user_integrations:
                    integrations_dict = [users_profile_utils.sqlalchemy_obj_to_dict(user_integrations)]
                    users_profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_integrations.json",
                        integrations_dict,
                        self.counts,
                    )
                else:
                    users_profile_utils.write_json_to_zip(zipf, "data/user_integrations.json", [], self.counts)
            except Exception as err:
                logger.error(f"Failed to collect user integrations: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect user integrations: {err}") from err

            # Collect and write user privacy settings
            try:
                user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                    self.user_id, self.db
                )
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
                logger.error(f"Failed to collect user privacy settings: {err}", exc_info=err)
                raise DataCollectionError(f"Failed to collect user privacy settings: {err}") from err

        except SQLAlchemyError as err:
            logger.error(f"Database error collecting user settings: {err}", exc_info=err)
            raise DatabaseConnectionError(f"Failed to collect user settings: {err}") from err

    def add_activity_files_to_zip(self, zipf: zipfile.ZipFile, user_activities: list[Any]):
        """
        Add activity files to ZIP archive.

        Reads each activity's retained source file through the platform
        ``StorageProvider`` (local disk or object storage) and writes it into the
        archive under ``activity_files/{id}{ext}``.

        Args:
            zipf: ZipFile instance to write to.
            user_activities: List of activity objects.
        """
        if not user_activities:
            return

        storage = platform_runtime.get_active_platform().storage
        for activity in user_activities:
            try:
                stored = activity_file_storage_service.get_activity_file(activity.id, storage)
                if stored is None:
                    continue
                key, data = stored
                zipf.writestr(os.path.join("activity_files", key), data)
                self.counts["activity_files"] += 1
            except MemoryAllocationError:
                raise
            except OSError as err:
                logger.warning(f"Failed to add activity file for activity {activity.id}: {err}", exc_info=err)
                continue
            except Exception as err:
                logger.warning(f"Unexpected error adding activity file for activity {activity.id}: {err}", exc_info=err)
                continue

    def add_activity_media_to_zip(self, zipf: zipfile.ZipFile, user_activities: list[Any]):
        """
        Add activity media files to ZIP archive.

        Read through the platform ``StorageProvider`` rather than by walking a
        local directory, so an export is complete regardless of which storage
        backend is configured. Keys are ``{activity_id}_{uuid}{ext}``, so each
        activity's blobs are listed by its own prefix instead of scanning every
        stored file and filtering.

        Args:
            zipf: ZipFile instance to write to.
            user_activities: List of activity objects.
        """
        if not user_activities:
            return

        storage = platform_runtime.get_active_platform().storage

        for activity in user_activities:
            try:
                keys = storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, f"{activity.id}_")
            except Exception as err:
                logger.warning(f"Failed to list media for activity {activity.id}: {err}", exc_info=err)
                continue

            for key in keys:
                try:
                    data = storage.get(activity_media_signing.MEDIA_STORAGE_AREA, key)
                    if data is None:
                        logger.warning(f"Media blob not found for key: {key}")
                        continue
                    zipf.writestr(os.path.join("activity_media", key), data)
                    self.counts["media"] += 1
                except MemoryAllocationError:
                    raise
                except Exception as err:
                    logger.warning(f"Unexpected error adding media file {key}: {err}", exc_info=err)
                    continue

    def add_user_images_to_zip(self, zipf: zipfile.ZipFile):
        """
        Add the user's profile image to the ZIP archive.

        Read through the platform ``StorageProvider`` rather than by walking a
        local directory, so an export is complete regardless of which storage
        backend is configured. Keys are ``{user_id}{ext}``, so the caller's
        blobs are listed by their own prefix instead of scanning every stored
        image and filtering by filename.

        Args:
            zipf: ZipFile instance to write to.
        """
        storage = platform_runtime.get_active_platform().storage
        area = users_signing.USER_IMAGE_STORAGE_AREA

        try:
            keys = storage.list_keys(area, f"{self.user_id}.")
        except Exception as err:
            logger.warning(f"Failed to list images for user {self.user_id}: {err}", exc_info=err)
            return

        for key in keys:
            try:
                data = storage.get(area, key)
                if data is None:
                    logger.warning(f"User image blob not found for key: {key}")
                    continue

                size = len(data)
                if size > 10 * 1024 * 1024:
                    logger.warning(f"Large image file: {key} ({size / (1024 * 1024):.1f}MB)")
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
                logger.warning(f"Unexpected error adding user image {key}: {err}", exc_info=err)

    def generate_export_archive(self, user_dict: dict[str, Any], timeout_seconds: int | None = 300) -> Generator[bytes]:
        """
        Generate and stream export archive as bytes.

        Args:
            user_dict: User data dictionary to export.
            timeout_seconds: Optional timeout in seconds.

        Yields:
            Chunks of ZIP archive as bytes.

        Raises:
            ExportTimeoutError: If operation times out.
            ZipCreationError: If ZIP creation fails.
            MemoryAllocationError: If memory limit exceeded.
            FileSystemError: If file system error occurs.
        """
        start_time = time.time()

        try:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                try:
                    compression_level = self.performance_config.compression_level
                    logger.info(f"Creating ZIP with compression level {compression_level}")

                    with zipfile.ZipFile(
                        tmp,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                        compresslevel=compression_level,
                    ) as zipf:
                        logger.info(f"Starting export for user {self.user_id}")

                        # Collect and write activities data progressively
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Collecting and writing activities data...")
                        user_activities = self.collect_user_activities_data(zipf)

                        # Collect and write gear data progressively
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Collecting and writing gear data...")
                        self.collect_gear_data(zipf)

                        # Collect and write health data progressively
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Collecting and writing health data...")
                        self.collect_health_weight(zipf)

                        # Collect and write settings data progressively
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Collecting and writing settings data...")
                        self.collect_user_settings_data(zipf)

                        # Write user data
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Writing user data...")
                        user_dict_list = [user_dict]
                        users_profile_utils.write_json_to_zip(zipf, "data/user.json", user_dict_list, self.counts)

                        # Add files to ZIP with timeout checks
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Adding activity files to archive...")
                        self.add_activity_files_to_zip(zipf, user_activities)

                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Adding activity media to archive...")
                        self.add_activity_media_to_zip(zipf, user_activities)

                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Adding user images to archive...")
                        self.add_user_images_to_zip(zipf)

                        # Write counts file
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info("Writing counts file...")
                        users_profile_utils.write_json_to_zip(zipf, "counts.json", [self.counts], self.counts)

                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        logger.info(f"Export completed successfully. Counts: {self.counts}")

                except zipfile.BadZipFile as err:
                    logger.error(f"ZIP creation error: {err}", exc_info=err)
                    raise ZipCreationError(f"Failed to create ZIP archive: {err}") from err
                except zipfile.LargeZipFile as err:
                    logger.error(f"ZIP file too large: {err}", exc_info=err)
                    raise ZipCreationError(f"Export archive too large: {err}") from err

                # Ensure all data is written to disk before streaming
                # This is critical for proper ZIP file structure and MIME type detection
                tmp.flush()
                os.fsync(tmp.fileno())

                # Get file size for logging
                file_size = tmp.tell()
                logger.info(f"ZIP archive created successfully: {file_size / (1024 * 1024):.2f}MB")

                # Stream the file with error handling
                tmp.seek(0)
                chunk_count = 0
                while True:
                    try:
                        users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                        chunk = tmp.read(8192)
                        if not chunk:
                            break
                        chunk_count += 1
                        yield chunk
                    except MemoryError as err:
                        logger.error(f"Memory error during streaming: {err}", exc_info=err)
                        raise MemoryAllocationError(f"Insufficient memory to stream export: {err}") from err

                logger.info(f"Successfully streamed {chunk_count} chunks for user {self.user_id}")
        except MemoryAllocationError as err:
            raise err
        except OSError as err:
            logger.error(f"File system error during export: {err}", exc_info=err)
            raise FileSystemError(f"File system error during export: {err}") from err
        except MemoryError as err:
            logger.error(f"Memory allocation error during export: {err}", exc_info=err)
            raise MemoryAllocationError(f"Insufficient memory for export: {err}") from err
