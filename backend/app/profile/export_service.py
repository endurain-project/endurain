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
import zipfile
import time
from typing import Generator, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import core.config as core_config
import core.logger as core_logger
from profile.exceptions import (
    DatabaseConnectionError,
    FileSystemError,
    ZipCreationError,
    MemoryAllocationError,
    DataCollectionError,
    ExportTimeoutError,
)
import profile.utils as profile_utils
import activities.activity.crud as activities_crud
import activities.activity_laps.crud as activity_laps_crud
import activities.activity_sets.crud as activity_sets_crud
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_workout_steps.crud as activity_workout_steps_crud
import activities.activity_media.crud as activity_media_crud
import activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import gears.gear.crud as gear_crud
import gears.gear_components.crud as gear_components_crud
import health.health_weight.crud as health_weight_crud
import health.health_targets.crud as health_targets_crud
import notifications.crud as notifications_crud
import users.user_default_gear.crud as user_default_gear_crud
import users.user_goals.crud as user_goals_crud
import users.user_identity_providers.crud as user_identity_providers_crud
import users.user_integrations.crud as user_integrations_crud
import users.user_privacy_settings.crud as users_privacy_settings_crud


class ExportPerformanceConfig(profile_utils.BasePerformanceConfig):
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
        super().__init__(
            batch_size, max_memory_mb, enable_memory_monitoring, timeout_seconds
        )
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
        self.counts = profile_utils.initialize_operation_counts(include_user_count=True)
        self.performance_config: ExportPerformanceConfig = (
            performance_config or ExportPerformanceConfig.get_auto_config()
        )

        core_logger.print_to_log(
            f"ExportService initialized with performance config: "
            f"batch_size={self.performance_config.batch_size}, "
            f"max_memory_mb={self.performance_config.max_memory_mb}, "
            f"compression_level={self.performance_config.compression_level}, "
            f"timeout_seconds={self.performance_config.timeout_seconds}",
            "info",
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
            profile_utils.check_memory_usage(
                "activity collection start",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            # Get activities in batches using pagination
            all_activities = []
            offset = 0
            batch_size = self.performance_config.batch_size

            core_logger.print_to_log(
                f"Starting batched activity collection with batch_size={batch_size}",
                "info",
            )

            while True:
                # Get a batch of activities
                batch_activities = self._get_activities_batch(offset, batch_size)

                if not batch_activities:
                    break

                all_activities.extend(batch_activities)
                offset += batch_size

                # Check memory usage after each batch
                profile_utils.check_memory_usage(
                    f"activity batch {offset//batch_size}",
                    self.performance_config.max_memory_mb,
                    self.performance_config.enable_memory_monitoring,
                )

                core_logger.print_to_log(
                    f"Collected {len(batch_activities)} activities in batch "
                    f"(total: {len(all_activities)})",
                    "info",
                )

            if not all_activities:
                core_logger.print_to_log(
                    f"No activities found for user {self.user_id}", "info"
                )
                # Write empty activities file
                profile_utils.write_json_to_zip(
                    zipf, "data/activities.json", [], self.counts
                )
                return []

            # Write activities to ZIP immediately
            activities_dicts = [
                profile_utils.sqlalchemy_obj_to_dict(a) for a in all_activities
            ]
            profile_utils.write_json_to_zip(
                zipf, "data/activities.json", activities_dicts, self.counts
            )

            core_logger.print_to_log(
                f"Written {len(activities_dicts)} activities to ZIP",
                "info",
            )

            # Filter out activities with None IDs and collect valid IDs
            activity_ids = [
                activity.id for activity in all_activities if activity.id is not None
            ]

            if not activity_ids:
                core_logger.print_to_log(
                    f"No valid activity IDs found for user {self.user_id}", "warning"
                )
                return all_activities

            # Collect and write activity components progressively
            self._collect_and_write_activity_components(
                zipf, activity_ids, all_activities
            )

            # Exercise titles don't depend on activity IDs
            try:
                exercise_titles = (
                    activity_exercise_titles_crud.get_activity_exercise_titles(self.db)
                )
                if exercise_titles:
                    exercise_titles_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(e) for e in exercise_titles
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/activity_exercise_titles.json",
                        exercise_titles_dicts,
                        self.counts,
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect exercise titles: {err}", "warning", exc=err
                )

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting activities: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect activity data: {err}"
            ) from err
        except MemoryAllocationError as err:
            core_logger.print_to_log(
                f"Memory limit exceeded while collecting activities: {err}. ",
                "error",
                exc=err,
            )
            raise err
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error collecting activities: {err}", "error", exc=err
            )
            raise DataCollectionError(
                f"Failed to collect activity data: {err}"
            ) from err

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

            # Use the existing pagination function from activities CRUD
            activities = activities_crud.get_user_activities_with_pagination(
                user_id=self.user_id,
                db=self.db,
                page_number=page_number,
                num_records=limit,
                # Sort by start_time descending (most recent first) for consistency
                sort_by="start_time",
                sort_order="desc",
                user_is_owner=True,
            )

            return activities or []

        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get activities batch (offset={offset}, limit={limit}): {err}",
                "warning",
                exc=err,
            )
            return []

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
        # Process activity IDs in smaller batches to reduce memory usage
        batch_size = (
            self.performance_config.batch_size // 2
        )  # Smaller batches for components

        # Component definitions: (key, filename, crud_function, should_split)
        component_types = [
            (
                "laps",
                "data/activity_laps.json",
                activity_laps_crud.get_activities_laps,
                True,
            ),
            (
                "sets",
                "data/activity_sets.json",
                activity_sets_crud.get_activities_sets,
                True,
            ),
            (
                "streams",
                "data/activity_streams.json",
                activity_streams_crud.get_activities_streams,
                True,
            ),
            (
                "steps",
                "data/activity_workout_steps.json",
                activity_workout_steps_crud.get_activities_workout_steps,
                False,
            ),
            (
                "media",
                "data/activity_media.json",
                activity_media_crud.get_activities_media,
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

            profile_utils.check_memory_usage(
                f"{component_key} batch {i//batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.user_id, self.db, batch_activities)
                if data:
                    # Convert to dicts and add to chunk buffer
                    batch_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(item) for item in data
                    ]
                    chunk_buffer.extend(batch_dicts)
                    total_items += len(batch_dicts)

                    # Write chunks to ZIP when buffer reaches max size
                    while len(chunk_buffer) >= max_items_per_file:
                        chunk_to_write = chunk_buffer[:max_items_per_file]
                        chunk_buffer = chunk_buffer[max_items_per_file:]

                        # Generate filename for this chunk
                        base_name = base_filename.rsplit(".", 1)[0]
                        extension = (
                            base_filename.rsplit(".", 1)[1]
                            if "." in base_filename
                            else "json"
                        )
                        chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

                        profile_utils.write_json_to_zip(
                            zipf, chunk_filename, chunk_to_write, self.counts
                        )
                        file_counter += 1

                        core_logger.print_to_log(
                            f"Written chunk {file_counter} for {component_key} ({len(chunk_to_write)} items)",
                            "debug",
                        )

            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect batch for {component_key}: {err}",
                    "warning",
                    exc=err,
                )

            core_logger.print_to_log(
                f"Processed {component_key} batch {i//batch_size + 1} "
                f"({len(batch_ids)} activities)",
                "info",
            )

        # Write remaining data in buffer
        if chunk_buffer:
            if file_counter == 0:
                # Only one chunk, use original filename
                profile_utils.write_json_to_zip(
                    zipf, base_filename, chunk_buffer, self.counts
                )
                core_logger.print_to_log(
                    f"Written {len(chunk_buffer)} {component_key} items to single file",
                    "info",
                )
            else:
                # Multiple chunks, write with numbered filename
                base_name = base_filename.rsplit(".", 1)[0]
                extension = (
                    base_filename.rsplit(".", 1)[1] if "." in base_filename else "json"
                )
                chunk_filename = f"{base_name}_{file_counter:03d}.{extension}"

                profile_utils.write_json_to_zip(
                    zipf, chunk_filename, chunk_buffer, self.counts
                )
                file_counter += 1
                core_logger.print_to_log(
                    f"Written final chunk for {component_key} ({len(chunk_buffer)} items)",
                    "debug",
                )

        if total_items == 0:
            # Write empty file for component type
            profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            core_logger.print_to_log(
                f"No {component_key} data found, written empty file",
                "info",
            )
        else:
            core_logger.print_to_log(
                f"Written total {total_items} {component_key} items to {file_counter} file(s)",
                "info",
            )

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

            profile_utils.check_memory_usage(
                f"{component_key} batch {i//batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            try:
                data = crud_func(batch_ids, self.user_id, self.db, batch_activities)
                if data:
                    all_component_data.extend(data)
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect batch for {component_key}: {err}",
                    "warning",
                    exc=err,
                )

            core_logger.print_to_log(
                f"Processed {component_key} batch {i//batch_size + 1} "
                f"({len(batch_ids)} activities)",
                "info",
            )

        # Write all component data to ZIP
        if all_component_data:
            component_dicts = [
                profile_utils.sqlalchemy_obj_to_dict(item)
                for item in all_component_data
            ]
            profile_utils.write_json_to_zip(
                zipf, base_filename, component_dicts, self.counts
            )
            core_logger.print_to_log(
                f"Written {len(component_dicts)} {component_key} items to ZIP",
                "info",
            )
            # Clear from memory
            all_component_data.clear()
            component_dicts.clear()
        else:
            # Write empty file for component type
            profile_utils.write_json_to_zip(zipf, base_filename, [], self.counts)
            core_logger.print_to_log(
                f"No {component_key} data found, written empty file",
                "info",
            )

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
                    gears_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(g) for g in gears
                    ]
                    profile_utils.write_json_to_zip(
                        zipf, "data/gears.json", gears_dicts, self.counts
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/gears.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect gears: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/gears.json", [], self.counts
                )

            # Collect and write gear components
            try:
                gear_components = gear_components_crud.get_gear_components_user(
                    self.user_id, self.db
                )
                if gear_components:
                    gear_components_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(gc)
                        for gc in gear_components
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/gear_components.json",
                        gear_components_dicts,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/gear_components.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect gear components: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/gear_components.json", [], self.counts
                )

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting gear data: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect gear data: {err}"
            ) from err

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
                health_weight = health_weight_crud.get_all_health_weight_by_user_id(
                    self.user_id, self.db
                )
                if health_weight:
                    health_weight_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(hd) for hd in health_weight
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/health_weight.json",
                        health_weight_dicts,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/health_weight.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect health data: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/health_weight.json", [], self.counts
                )

            # Collect and write health targets
            try:
                health_targets = health_targets_crud.get_health_targets_by_user_id(
                    self.user_id, self.db
                )
                if health_targets:
                    # health_targets is a single object, not a list
                    health_targets_dict = profile_utils.sqlalchemy_obj_to_dict(
                        health_targets
                    )
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/health_targets.json",
                        [health_targets_dict],
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/health_targets.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect health targets: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/health_targets.json", [], self.counts
                )

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting health data: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect health data: {err}"
            ) from err

    def collect_notifications_data(self, zipf: zipfile.ZipFile) -> None:
        try:
            try:
                notifications = notifications_crud.get_user_notifications(
                    self.user_id, self.db
                )
                if notifications:
                    notifications_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(n) for n in notifications
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/notifications.json",
                        notifications_dicts,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/notifications.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user notifications: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/notifications.json", [], self.counts
                )
        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting user notifications: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect user notifications: {err}"
            ) from err

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
                user_default_gear = (
                    user_default_gear_crud.get_user_default_gear_by_user_id(
                        self.user_id, self.db
                    )
                )
                if user_default_gear:
                    default_gear_dict = [
                        profile_utils.sqlalchemy_obj_to_dict(user_default_gear)
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_default_gear.json",
                        default_gear_dict,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_default_gear.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user default gear: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/user_default_gear.json", [], self.counts
                )

            # Collect and write user goals
            try:
                user_goals = user_goals_crud.get_user_goals_by_user_id(
                    self.user_id, self.db
                )
                if user_goals:
                    user_goals_dicts = [
                        profile_utils.sqlalchemy_obj_to_dict(ug) for ug in user_goals
                    ]
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_goals.json", user_goals_dicts, self.counts
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_goals.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user goals: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/user_goals.json", [], self.counts
                )

            # Collect and write user identity providers
            try:
                user_identity_providers = (
                    user_identity_providers_crud.get_user_identity_providers_by_user_id(
                        self.user_id, self.db
                    )
                )
                if user_identity_providers:
                    identity_providers_dict = [
                        profile_utils.sqlalchemy_obj_to_dict(uidp)
                        for uidp in user_identity_providers
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_identity_providers.json",
                        identity_providers_dict,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_identity_providers.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user identity providers: {err}",
                    "warning",
                    exc=err,
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/user_identity_providers.json", [], self.counts
                )

            # Collect and write user integrations
            try:
                user_integrations = (
                    user_integrations_crud.get_user_integrations_by_user_id(
                        self.user_id, self.db
                    )
                )
                if user_integrations:
                    integrations_dict = [
                        profile_utils.sqlalchemy_obj_to_dict(user_integrations)
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_integrations.json",
                        integrations_dict,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_integrations.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user integrations: {err}", "warning", exc=err
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/user_integrations.json", [], self.counts
                )

            # Collect and write user privacy settings
            try:
                user_privacy_settings = (
                    users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                        self.user_id, self.db
                    )
                )
                if user_privacy_settings:
                    privacy_dict = [
                        profile_utils.sqlalchemy_obj_to_dict(user_privacy_settings)
                    ]
                    profile_utils.write_json_to_zip(
                        zipf,
                        "data/user_privacy_settings.json",
                        privacy_dict,
                        self.counts,
                    )
                else:
                    profile_utils.write_json_to_zip(
                        zipf, "data/user_privacy_settings.json", [], self.counts
                    )
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user privacy settings: {err}",
                    "warning",
                    exc=err,
                )
                profile_utils.write_json_to_zip(
                    zipf, "data/user_privacy_settings.json", [], self.counts
                )

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting user settings: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect user settings: {err}"
            ) from err

    def add_activity_files_to_zip(
        self, zipf: zipfile.ZipFile, user_activities: list[Any]
    ):
        """
        Add activity files to ZIP archive.

        Args:
            zipf: ZipFile instance to write to.
            user_activities: List of activity objects.

        Raises:
            FileSystemError: If file system error occurs.
        """
        if not user_activities:
            return

        try:
            if not os.path.exists(core_config.FILES_PROCESSED_DIR):
                core_logger.print_to_log(
                    f"Files directory does not exist: {core_config.FILES_PROCESSED_DIR}",
                    "warning",
                )
                return

            for root, _, files in os.walk(core_config.FILES_PROCESSED_DIR):
                for file in files:
                    try:
                        file_id, _ = os.path.splitext(file)
                        if any(
                            str(activity.id) == file_id for activity in user_activities
                        ):
                            file_path = os.path.join(root, file)

                            # Check if file exists and is readable
                            if not os.path.isfile(file_path):
                                core_logger.print_to_log(
                                    f"Activity file not found: {file_path}", "warning"
                                )
                                continue

                            arcname = os.path.join(
                                "activity_files",
                                os.path.relpath(
                                    file_path, core_config.FILES_PROCESSED_DIR
                                ),
                            )
                            zipf.write(file_path, arcname)
                            self.counts["activity_files"] += 1

                    except (OSError, IOError) as err:
                        core_logger.print_to_log(
                            f"Failed to add activity file {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue
                    except Exception as err:
                        core_logger.print_to_log(
                            f"Unexpected error adding activity file {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue

        except (OSError, IOError) as err:
            core_logger.print_to_log(
                f"File system error accessing activity files: {err}", "error", exc=err
            )
            raise FileSystemError(
                f"Cannot access activity files directory: {err}"
            ) from err

    def add_activity_media_to_zip(
        self, zipf: zipfile.ZipFile, user_activities: list[Any]
    ):
        """
        Add activity media files to ZIP archive.

        Args:
            zipf: ZipFile instance to write to.
            user_activities: List of activity objects.

        Raises:
            FileSystemError: If file system error occurs.
        """
        if not user_activities:
            return

        try:
            if not os.path.exists(core_config.ACTIVITY_MEDIA_DIR):
                core_logger.print_to_log(
                    f"Media directory does not exist: {core_config.ACTIVITY_MEDIA_DIR}",
                    "warning",
                )
                return

            for root, _, files in os.walk(core_config.ACTIVITY_MEDIA_DIR):
                for file in files:
                    try:
                        file_id, _ = os.path.splitext(file)
                        file_activity_id = file_id.split("_")[0]

                        if any(
                            str(activity.id) == file_activity_id
                            for activity in user_activities
                        ):
                            file_path = os.path.join(root, file)

                            # Check if file exists and is readable
                            if not os.path.isfile(file_path):
                                core_logger.print_to_log(
                                    f"Media file not found: {file_path}", "warning"
                                )
                                continue

                            arcname = os.path.join(
                                "activity_media",
                                os.path.relpath(
                                    file_path, core_config.ACTIVITY_MEDIA_DIR
                                ),
                            )
                            zipf.write(file_path, arcname)
                            self.counts["media"] += 1

                    except (OSError, IOError) as err:
                        core_logger.print_to_log(
                            f"Failed to add media file {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue
                    except Exception as err:
                        core_logger.print_to_log(
                            f"Unexpected error adding media file {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue

        except (OSError, IOError) as err:
            core_logger.print_to_log(
                f"File system error accessing media files: {err}", "error", exc=err
            )
            raise FileSystemError(
                f"Cannot access media files directory: {err}"
            ) from err

    def add_user_images_to_zip(self, zipf: zipfile.ZipFile):
        """
        Add user image files to ZIP archive.

        Args:
            zipf: ZipFile instance to write to.

        Raises:
            FileSystemError: If file system error occurs.
        """
        try:
            if not os.path.exists(core_config.USER_IMAGES_DIR):
                core_logger.print_to_log(
                    f"User images directory does not exist: {core_config.USER_IMAGES_DIR}",
                    "warning",
                )
                return

            self._add_user_images_optimized(zipf, core_config.USER_IMAGES_DIR)

        except Exception as err:
            core_logger.print_to_log(
                f"Error adding user images to ZIP: {err}", "error", exc=err
            )
            raise FileSystemError(f"Failed to add user images: {err}") from err

    def _add_user_images_optimized(self, zipf: zipfile.ZipFile, images_dir: str):
        """
        Recursively add user images from directory.

        Args:
            zipf: ZipFile instance to write to.
            images_dir: Directory path containing images.
        """
        try:
            with os.scandir(images_dir) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False):
                        self._process_user_image_file(zipf, entry, images_dir)
                    elif entry.is_dir(follow_symlinks=False):
                        # Recursively process subdirectories
                        self._add_user_images_optimized(zipf, entry.path)
        except PermissionError as err:
            core_logger.print_to_log(
                f"Permission denied accessing {images_dir}: {err}", "warning"
            )
        except OSError as err:
            core_logger.print_to_log(
                f"OS error accessing {images_dir}: {err}", "warning"
            )

    def _process_user_image_file(self, zipf: zipfile.ZipFile, entry, images_dir: str):
        """
        Process and add single user image file to ZIP.

        Args:
            zipf: ZipFile instance to write to.
            entry: Directory entry for the image file.
            images_dir: Base images directory path.
        """
        try:
            file_id, _ = os.path.splitext(entry.name)
            if str(self.user_id) == file_id:
                # Get file size for monitoring
                file_size = entry.stat().st_size

                # Warn about large image files (>10MB)
                if file_size > 10 * 1024 * 1024:
                    core_logger.print_to_log(
                        f"Large image file: {entry.path} ({file_size / (1024*1024):.1f}MB)",
                        "warning",
                    )

                # Check memory usage before adding large files
                if file_size > 5 * 1024 * 1024:  # 5MB threshold for images
                    profile_utils.check_memory_usage(
                        f"before image {entry.name}",
                        self.performance_config.max_memory_mb,
                        self.performance_config.enable_memory_monitoring,
                    )

                arcname = os.path.join(
                    "user_images",
                    os.path.relpath(entry.path, images_dir),
                )
                zipf.write(entry.path, arcname)
                self.counts["user_images"] += 1

        except FileNotFoundError:
            core_logger.print_to_log(f"Image file not found: {entry.path}", "warning")
        except PermissionError:
            core_logger.print_to_log(f"Permission denied: {entry.path}", "warning")
        except OSError as err:
            core_logger.print_to_log(
                f"Error processing image {entry.path}: {err}", "warning"
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error with image {entry.path}: {err}", "warning", exc=err
            )

    def generate_export_archive(
        self, user_dict: dict[str, Any], timeout_seconds: int | None = 300
    ) -> Generator[bytes, None, None]:
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
                    core_logger.print_to_log(
                        f"Creating ZIP with compression level {compression_level}",
                        "info",
                    )

                    with zipfile.ZipFile(
                        tmp,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                        compresslevel=compression_level,
                    ) as zipf:
                        core_logger.print_to_log(
                            f"Starting export for user {self.user_id}", "info"
                        )

                        # Collect and write activities data progressively
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting and writing activities data...", "info"
                        )
                        user_activities = self.collect_user_activities_data(zipf)

                        # Collect and write gear data progressively
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting and writing gear data...", "info"
                        )
                        self.collect_gear_data(zipf)

                        # Collect and write health data progressively
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting and writing health data...", "info"
                        )
                        self.collect_health_weight(zipf)

                        # Collect and write notifications progressively
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting and writing notifications data...", "info"
                        )
                        self.collect_notifications_data(zipf)

                        # Collect and write settings data progressively
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting and writing settings data...", "info"
                        )
                        self.collect_user_settings_data(zipf)

                        # Write user data
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Writing user data...", "info")
                        user_dict_list = [user_dict]
                        profile_utils.write_json_to_zip(
                            zipf, "data/user.json", user_dict_list, self.counts
                        )

                        # Add files to ZIP with timeout checks
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Adding activity files to archive...", "info"
                        )
                        self.add_activity_files_to_zip(zipf, user_activities)

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Adding activity media to archive...", "info"
                        )
                        self.add_activity_media_to_zip(zipf, user_activities)

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Adding user images to archive...", "info"
                        )
                        self.add_user_images_to_zip(zipf)

                        # Write counts file
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Writing counts file...", "info")
                        profile_utils.write_json_to_zip(
                            zipf, "counts.json", [self.counts], self.counts
                        )

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            f"Export completed successfully. Counts: {self.counts}",
                            "info",
                        )

                except zipfile.BadZipFile as err:
                    core_logger.print_to_log(
                        f"ZIP creation error: {err}", "error", exc=err
                    )
                    raise ZipCreationError(
                        f"Failed to create ZIP archive: {err}"
                    ) from err
                except zipfile.LargeZipFile as err:
                    core_logger.print_to_log(
                        f"ZIP file too large: {err}", "error", exc=err
                    )
                    raise ZipCreationError(f"Export archive too large: {err}") from err
                except MemoryAllocationError as err:
                    raise err
                except Exception as err:
                    raise err

                # Ensure all data is written to disk before streaming
                # This is critical for proper ZIP file structure and MIME type detection
                tmp.flush()
                os.fsync(tmp.fileno())

                # Get file size for logging
                file_size = tmp.tell()
                core_logger.print_to_log(
                    f"ZIP archive created successfully: {file_size / (1024*1024):.2f}MB",
                    "info",
                )

                # Stream the file with error handling
                tmp.seek(0)
                chunk_count = 0
                while True:
                    try:
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        chunk = tmp.read(8192)
                        if not chunk:
                            break
                        chunk_count += 1
                        yield chunk
                    except MemoryError as err:
                        core_logger.print_to_log(
                            f"Memory error during streaming: {err}", "error", exc=err
                        )
                        raise MemoryAllocationError(
                            f"Insufficient memory to stream export: {err}"
                        ) from err

                core_logger.print_to_log(
                    f"Successfully streamed {chunk_count} chunks for user {self.user_id}",
                    "info",
                )
        except MemoryAllocationError as err:
            raise err
        except OSError as err:
            core_logger.print_to_log(
                f"File system error during export: {err}", "error", exc=err
            )
            raise FileSystemError(f"File system error during export: {err}") from err
        except MemoryError as err:
            core_logger.print_to_log(
                f"Memory allocation error during export: {err}", "error", exc=err
            )
            raise MemoryAllocationError(
                f"Insufficient memory for export: {err}"
            ) from err
