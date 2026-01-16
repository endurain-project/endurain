"""Profile data import service for ZIP archive processing.

This module provides the ImportService class for importing
user profile data from ZIP archives.

Key Features:
- ZIP validation and security checks
- Batched data processing
- WebSocket progress updates
- Automatic performance tier detection
- Memory and timeout monitoring
"""

import os
import json
import zipfile
import time
from io import BytesIO
from typing import Any
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger

from profile.exceptions import (
    FileFormatError,
    ImportTimeoutError,
    FileSizeError,
    ActivityLimitError,
    JSONParseError,
    FileSystemError,
)

import profile.utils as profile_utils

import users.user.crud as users_crud
import users.user.schema as users_schema

import users.user_default_gear.crud as user_default_gear_crud
import users.user_default_gear.schema as user_default_gear_schema

import users.user_goals.crud as user_goals_crud
import users.user_goals.schema as user_goals_schema

import users.user_identity_providers.crud as user_identity_providers_crud
import users.user_identity_providers.schema as user_identity_providers_schema

import users.user_integrations.crud as user_integrations_crud
import users.user_integrations.schema as users_integrations_schema

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import activities.activity.crud as activities_crud
import activities.activity.schema as activity_schema

import activities.activity_laps.crud as activity_laps_crud

import activities.activity_media.crud as activity_media_crud
import activities.activity_media.schema as activity_media_schema

import activities.activity_sets.crud as activity_sets_crud
import activities.activity_sets.schema as activity_sets_schema

import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.schema as activity_streams_schema

import activities.activity_workout_steps.crud as activity_workout_steps_crud
import activities.activity_workout_steps.schema as activity_workout_steps_schema

import activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import activities.activity_exercise_titles.schema as activity_exercise_titles_schema

import gears.gear.crud as gear_crud
import gears.gear.schema as gear_schema

import gears.gear_components.crud as gear_components_crud
import gears.gear_components.schema as gear_components_schema

import notifications.crud as notifications_crud
import notifications.schema as notifications_schema

import health.health_weight.crud as health_weight_crud
import health.health_weight.schema as health_weight_schema

import health.health_targets.crud as health_targets_crud
import health.health_targets.schema as health_targets_schema

import websocket.manager as websocket_manager


class ImportPerformanceConfig(profile_utils.BasePerformanceConfig):
    """
    Performance configuration for import operations.

    Attributes:
        batch_size: Number of items per batch.
        max_memory_mb: Maximum memory in megabytes.
        max_file_size_mb: Maximum file size in megabytes.
        max_activities: Maximum number of activities.
        timeout_seconds: Operation timeout in seconds.
        chunk_size: Data chunk size in bytes.
        enable_memory_monitoring: Enable memory monitoring.
    """

    def __init__(
        self,
        batch_size: int = 125,
        max_memory_mb: int = 1024,
        max_file_size_mb: int = 1000,
        max_activities: int = 10000,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        super().__init__(
            batch_size=batch_size,
            max_memory_mb=max_memory_mb,
            timeout_seconds=timeout_seconds,
            chunk_size=chunk_size,
            enable_memory_monitoring=enable_memory_monitoring,
        )
        self.max_file_size_mb = max_file_size_mb
        self.max_activities = max_activities

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
                "max_file_size_mb": 2000,
                "max_activities": 20000,
                "timeout_seconds": 7200,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "medium": {
                "batch_size": 125,
                "max_memory_mb": 1024,
                "max_file_size_mb": 1000,
                "max_activities": 10000,
                "timeout_seconds": 3600,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "low": {
                "batch_size": 50,
                "max_memory_mb": 512,
                "max_file_size_mb": 500,
                "max_activities": 5000,
                "timeout_seconds": 1800,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
        }


class ImportService:
    """
    Service for importing user profile data from ZIP archive.

    Attributes:
        user_id: ID of user to import data for.
        db: Database session.
        websocket_manager: WebSocket manager for updates.
        counts: Dictionary tracking imported item counts.
        performance_config: Performance configuration.
    """

    def __init__(
        self,
        user_id: int,
        db: Session,
        websocket_manager: websocket_manager.WebSocketManager,
        performance_config: ImportPerformanceConfig | None = None,
    ):
        self.user_id = user_id
        self.db = db
        self.websocket_manager = websocket_manager
        self.counts = profile_utils.initialize_operation_counts(
            include_user_count=False
        )
        self.performance_config: ImportPerformanceConfig = (
            performance_config or ImportPerformanceConfig.get_auto_config()
        )

        core_logger.print_to_log(
            f"ImportService initialized with performance config: "
            f"batch_size={self.performance_config.batch_size}, "
            f"max_memory_mb={self.performance_config.max_memory_mb}, "
            f"max_file_size_mb={self.performance_config.max_file_size_mb}, "
            f"timeout_seconds={self.performance_config.timeout_seconds}",
            "info",
        )

    async def import_from_zip_data(self, zip_data: bytes) -> dict[str, Any]:
        """
        Import profile data from ZIP file bytes.

        Args:
            zip_data: ZIP file content as bytes.

        Returns:
            Dictionary with import results and counts.

        Raises:
            FileSizeError: If file exceeds size limit.
            FileFormatError: If ZIP format is invalid.
            FileSystemError: If file system error occurs.
            ImportTimeoutError: If operation times out.
        """
        start_time = time.time()
        timeout_seconds = self.performance_config.timeout_seconds

        # Check file size
        file_size_mb = len(zip_data) / (1024 * 1024)
        if file_size_mb > self.performance_config.max_file_size_mb:
            raise FileSizeError(
                f"ZIP file size ({file_size_mb:.1f}MB) exceeds maximum allowed "
                f"({self.performance_config.max_file_size_mb}MB)"
            )

        # Early memory check BEFORE loading any data
        profile_utils.check_memory_usage(
            "pre-import memory check",
            self.performance_config.max_memory_mb,
            self.performance_config.enable_memory_monitoring,
        )

        try:
            with zipfile.ZipFile(BytesIO(zip_data)) as zipf:
                file_list = set(zipf.namelist())

                # Create ID mappings for relationships
                gears_id_mapping = {}
                activities_id_mapping = {}

                # Import data in dependency order using streaming approach
                # Load and import gears
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                gears_data = self._load_single_json(zipf, "data/gears.json")
                gears_id_mapping = await self.collect_and_import_gears_data(gears_data)
                del gears_data  # Explicit memory cleanup

                # Load and import gear components
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                gear_components_data = self._load_single_json(
                    zipf, "data/gear_components.json"
                )
                await self.collect_and_import_gear_components_data(
                    gear_components_data, gears_id_mapping
                )
                del gear_components_data

                # Load and import user data (includes user, default gear, integrations, goals, privacy)
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                user_data = self._load_single_json(zipf, "data/user.json")
                user_default_gear_data = self._load_single_json(
                    zipf, "data/user_default_gear.json"
                )
                user_goals_data = self._load_single_json(zipf, "data/user_goals.json")
                user_identity_providers_data = self._load_single_json(
                    zipf, "data/user_identity_providers.json"
                )
                user_integrations_data = self._load_single_json(
                    zipf, "data/user_integrations.json"
                )
                user_privacy_settings_data = self._load_single_json(
                    zipf, "data/user_privacy_settings.json"
                )

                await self.collect_and_import_user_data(
                    user_data,
                    user_default_gear_data,
                    user_goals_data,
                    user_identity_providers_data,
                    user_integrations_data,
                    user_privacy_settings_data,
                    gears_id_mapping,
                )
                del user_data, user_default_gear_data, user_integrations_data
                del user_goals_data, user_privacy_settings_data

                # Load and import activities with their components
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )

                # Import activities and components using batched approach to avoid memory issues
                activities_id_mapping = (
                    await self.collect_and_import_activities_data_batched(
                        zipf,
                        file_list,
                        gears_id_mapping,
                        start_time,
                        timeout_seconds,
                    )
                )

                # Load and import notifications
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                notifications_data = self._load_single_json(
                    zipf, "data/notifications.json"
                )

                await self.collect_and_import_notifications_data(notifications_data)
                del notifications_data

                # Load and import health data
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                health_weight_data = self._load_single_json(
                    zipf, "data/health_weight.json"
                )
                health_targets_data = self._load_single_json(
                    zipf, "data/health_targets.json"
                )

                await self.collect_and_import_health_weight(
                    health_weight_data, health_targets_data
                )
                del health_weight_data, health_targets_data

                # Import files and media
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                await self.add_activity_files_from_zip(
                    zipf, file_list, activities_id_mapping
                )
                await self.add_activity_media_from_zip(
                    zipf, file_list, activities_id_mapping
                )
                await self.add_user_images_from_zip(zipf, file_list)

        except zipfile.BadZipFile as e:
            raise FileFormatError(f"Invalid ZIP file format: {str(e)}") from e
        except (OSError, IOError) as e:
            raise FileSystemError(f"File system error during import: {str(e)}") from e

        return {"detail": "Import completed", "imported": self.counts}

    def _load_single_json(
        self, zipf: zipfile.ZipFile, filename: str, check_memory: bool = True
    ) -> list[Any]:
        """
        Load and parse JSON file from ZIP archive.

        Args:
            zipf: ZipFile instance to read from.
            filename: Name of JSON file to load.
            check_memory: Whether to check memory usage.

        Returns:
            Parsed JSON data as list.

        Raises:
            JSONParseError: If JSON parsing fails.
        """
        try:
            file_list = set(zipf.namelist())
            if filename not in file_list:
                return []

            data = json.loads(zipf.read(filename))
            core_logger.print_to_log(
                f"Loaded {len(data) if isinstance(data, list) else 1} items from {filename}",
                "debug",
            )

            if check_memory:
                profile_utils.check_memory_usage(
                    f"loading {filename}",
                    self.performance_config.max_memory_mb,
                    self.performance_config.enable_memory_monitoring,
                )

            return data
        except json.JSONDecodeError as err:
            error_msg = f"Failed to parse JSON from {filename}: {err}"
            core_logger.print_to_log(error_msg, "error")
            raise JSONParseError(error_msg) from err

    async def collect_and_import_gears_data(
        self, gears_data: list[Any]
    ) -> dict[int, int]:
        """
        Import gear data and create ID mappings.

        Args:
            gears_data: List of gear data dictionaries.

        Returns:
            Dictionary mapping old gear IDs to new IDs.
        """
        gears_id_mapping = {}

        if not gears_data:
            core_logger.print_to_log("No gears data to import", "info")
            return gears_id_mapping

        for gear_data in gears_data:
            gear_data["user_id"] = self.user_id
            original_id = gear_data.get("id")
            gear_data.pop("id", None)

            gear = gear_schema.Gear(**gear_data)
            new_gear = gear_crud.create_gear(gear, self.user_id, self.db)
            gears_id_mapping[original_id] = new_gear.id
            self.counts["gears"] += 1

        core_logger.print_to_log(f"Imported {self.counts['gears']} gears", "info")
        return gears_id_mapping

    async def collect_and_import_gear_components_data(
        self, gear_components_data: list[Any], gears_id_mapping: dict[int, int]
    ) -> None:
        """
        Import gear components data with ID remapping.

        Args:
            gear_components_data: List of component dicts.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if not gear_components_data:
            core_logger.print_to_log("No gear components data to import", "info")
            return

        for gear_component_data in gear_components_data:
            gear_component_data["user_id"] = self.user_id
            gear_component_data["gear_id"] = (
                gears_id_mapping.get(gear_component_data["gear_id"])
                if gear_component_data.get("gear_id") in gears_id_mapping
                else None
            )

            gear_component_data.pop("id", None)

            gear_component = gear_components_schema.GearComponents(
                **gear_component_data
            )
            gear_components_crud.create_gear_component(
                gear_component, self.user_id, self.db
            )
            self.counts["gear_components"] += 1

        core_logger.print_to_log(
            f"Imported {self.counts['gear_components']} gear components", "info"
        )

    async def collect_and_import_user_data(
        self,
        user_data: list[Any],
        user_default_gear_data: list[Any],
        user_goals_data: list[Any],
        user_identity_providers_data: list[Any],
        user_integrations_data: list[Any],
        user_privacy_settings_data: list[Any],
        gears_id_mapping: dict[int, int],
    ) -> None:
        """
        Import user profile and related settings.

        Args:
            user_data: User profile data.
            user_default_gear_data: Default gear settings.
            user_goals_data: User goals data.
            user_identity_providers_data: Identity providers data.
            user_integrations_data: Integration settings.
            user_privacy_settings_data: Privacy settings.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if not user_data:
            core_logger.print_to_log("No user data to import", "info")
            return

        # Import user profile
        user_profile = user_data[0]
        user_profile["id"] = self.user_id

        # Handle photo path
        photo_path = user_profile.get("photo_path")
        if isinstance(photo_path, str) and photo_path.startswith("data/user_images/"):
            extension = photo_path.split(".")[-1]
            user_profile["photo_path"] = f"data/user_images/{self.user_id}.{extension}"

        user = users_schema.UserRead(**user_profile)
        users_crud.edit_user(self.user_id, user, self.db)
        self.counts["user"] += 1

        # Import user-related settings
        await self.collect_and_import_user_default_gear(
            user_default_gear_data, gears_id_mapping
        )
        await self.collect_and_import_user_goals(user_goals_data)
        await self.collect_and_import_user_identity_providers(
            user_identity_providers_data
        )
        await self.collect_and_import_user_integrations(user_integrations_data)
        await self.collect_and_import_user_privacy_settings(user_privacy_settings_data)

    async def collect_and_import_user_default_gear(
        self, user_default_gear_data: list[Any], gears_id_mapping: dict[int, int]
    ) -> None:
        """
        Import user default gear settings with ID remapping.

        Args:
            user_default_gear_data: Default gear data.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if not user_default_gear_data:
            core_logger.print_to_log("No user default gear data to import", "info")
            return

        current_user_default_gear = (
            user_default_gear_crud.get_user_default_gear_by_user_id(
                self.user_id, self.db
            )
        )

        if current_user_default_gear is None:
            core_logger.print_to_log("No existing user default gear to update", "info")
            return

        gear_data = user_default_gear_data[0]
        gear_data["id"] = current_user_default_gear.id
        gear_data["user_id"] = self.user_id

        # Map gear IDs
        gear_fields = [
            "run_gear_id",
            "trail_run_gear_id",
            "virtual_run_gear_id",
            "ride_gear_id",
            "gravel_ride_gear_id",
            "mtb_ride_gear_id",
            "virtual_ride_gear_id",
            "ows_gear_id",
            "walk_gear_id",
            "hike_gear_id",
            "tennis_gear_id",
            "alpine_ski_gear_id",
            "nordic_ski_gear_id",
            "snowboard_gear_id",
            "windsurf_gear_id",
        ]

        for field in gear_fields:
            old_gear_id = gear_data.get(field)
            if old_gear_id in gears_id_mapping:
                gear_data[field] = gears_id_mapping[old_gear_id]
            else:
                gear_data[field] = None

        user_default_gear = user_default_gear_schema.UserDefaultGearUpdate(**gear_data)
        user_default_gear_crud.edit_user_default_gear(
            user_default_gear, self.user_id, self.db
        )
        core_logger.print_to_log(f"Imported user default gear", "info")
        self.counts["user_default_gear"] += 1

    async def collect_and_import_user_integrations(
        self, user_integrations_data: list[Any]
    ) -> None:
        """
        Import user integration settings.

        Args:
            user_integrations_data: Integration data.
        """
        if not user_integrations_data:
            core_logger.print_to_log("No user integrations data to import", "info")
            return

        integrations_data = user_integrations_data[0]

        user_integrations = users_integrations_schema.UsersIntegrationsUpdate(
            **integrations_data
        )
        user_integrations_crud.edit_user_integrations(
            user_integrations, self.user_id, self.db
        )
        core_logger.print_to_log(f"Imported user integrations", "info")
        self.counts["user_integrations"] += 1

    async def collect_and_import_user_goals(self, user_goals_data: list[Any]) -> None:
        """
        Import user goals data.

        Args:
            user_goals_data: List of user goal dictionaries.
        """
        if not user_goals_data:
            core_logger.print_to_log("No user goals data to import", "info")
            return

        for goal_data in user_goals_data:
            goal_data.pop("id", None)
            goal_data.pop("user_id", None)

            goal = user_goals_schema.UserGoalCreate(**goal_data)
            user_goals_crud.create_user_goal(self.user_id, goal, self.db)
            self.counts["user_goals"] += 1

        core_logger.print_to_log(
            f"Imported {self.counts['user_goals']} user goals", "info"
        )

    async def collect_and_import_user_identity_providers(
        self, user_identity_providers_data: list[Any]
    ) -> None:
        """
        Import user identity provider links.

        Args:
            user_identity_providers_data: Identity provider data.
        """
        if not user_identity_providers_data:
            core_logger.print_to_log(
                "No user identity providers data to import", "info"
            )
            return

        for provider_data in user_identity_providers_data:
            provider_data.pop("id", None)
            provider_data.pop("user_id", None)

            user_identity_providers_crud.create_user_identity_provider(
                self.user_id, provider_data.id, provider_data.idp_subject, self.db
            )
            self.counts["user_identity_providers"] += 1

        core_logger.print_to_log(
            f"Imported {self.counts['user_identity_providers']} user identity providers",
            "info",
        )

    async def collect_and_import_user_privacy_settings(
        self, user_privacy_settings_data: list[Any]
    ) -> None:
        """
        Import user privacy settings.

        Args:
            user_privacy_settings_data: Privacy settings data.
        """
        if not user_privacy_settings_data:
            core_logger.print_to_log("No user privacy settings data to import", "info")
            return

        privacy_data = user_privacy_settings_data[0]

        user_privacy_settings = (
            users_privacy_settings_schema.UsersPrivacySettingsUpdate(**privacy_data)
        )
        users_privacy_settings_crud.edit_user_privacy_settings(
            self.user_id, user_privacy_settings, self.db
        )
        core_logger.print_to_log(f"Imported user privacy settings", "info")
        self.counts["user_privacy_settings"] += 1

    async def collect_and_import_activity_components(
        self,
        activity_laps_data: list[Any],
        activity_sets_data: list[Any],
        activity_streams_data: list[Any],
        activity_workout_steps_data: list[Any],
        activity_media_data: list[Any],
        activity_exercise_titles_data: list[Any],
        original_activity_id: int,
        new_activity_id: int,
    ) -> None:
        """
        Import all components for a single activity.

        Args:
            activity_laps_data: Laps data for all activities.
            activity_sets_data: Sets data for all activities.
            activity_streams_data: Streams data.
            activity_workout_steps_data: Workout steps data.
            activity_media_data: Media data for all activities.
            activity_exercise_titles_data: Exercise titles.
            original_activity_id: Old activity ID.
            new_activity_id: New activity ID.
        """
        # Import laps - filter for this activity
        if activity_laps_data:
            laps = []
            laps_for_activity = [
                lap
                for lap in activity_laps_data
                if lap.get("activity_id") == original_activity_id
            ]
            for lap_data in laps_for_activity:
                lap_data.pop("id", None)
                lap_data["activity_id"] = new_activity_id
                laps.append(lap_data)

            if laps:
                activity_laps_crud.create_activity_laps(laps, new_activity_id, self.db)
                self.counts["activity_laps"] += len(laps)

        # Import sets - filter for this activity
        if activity_sets_data:
            sets = []
            sets_for_activity = [
                activity_set
                for activity_set in activity_sets_data
                if activity_set.get("activity_id") == original_activity_id
            ]
            for activity_set in sets_for_activity:
                activity_set.pop("id", None)
                activity_set["activity_id"] = new_activity_id
                set_activity = activity_sets_schema.ActivitySets(**activity_set)
                sets.append(set_activity)

            if sets:
                activity_sets_crud.create_activity_sets(sets, new_activity_id, self.db)
                self.counts["activity_sets"] += len(sets)

        # Import streams - filter for this activity
        if activity_streams_data:
            streams = []
            streams_for_activity = [
                stream
                for stream in activity_streams_data
                if stream.get("activity_id") == original_activity_id
            ]
            for stream_data in streams_for_activity:
                stream_data.pop("id", None)
                stream_data["activity_id"] = new_activity_id
                stream = activity_streams_schema.ActivityStreams(**stream_data)
                streams.append(stream)

            if streams:
                activity_streams_crud.create_activity_streams(streams, self.db)
                self.counts["activity_streams"] += len(streams)

        # Import workout steps
        if activity_workout_steps_data:
            steps = []
            steps_for_activity = [
                step
                for step in activity_workout_steps_data
                if step.get("activity_id") == original_activity_id
            ]
            for step_data in steps_for_activity:
                step_data.pop("id", None)
                step_data["activity_id"] = new_activity_id
                step = activity_workout_steps_schema.ActivityWorkoutSteps(**step_data)
                steps.append(step)

            if steps:
                activity_workout_steps_crud.create_activity_workout_steps(
                    steps, new_activity_id, self.db
                )
                self.counts["activity_workout_steps"] += len(steps)

        # Import media
        if activity_media_data:
            media = []
            media_for_activity = [
                media_item
                for media_item in activity_media_data
                if media_item.get("activity_id") == original_activity_id
            ]
            for media_data in media_for_activity:
                media_data.pop("id", None)
                media_data["activity_id"] = new_activity_id

                # Update media path
                old_path = media_data.get("media_path", None)
                if old_path:
                    filename = old_path.split("/")[-1]
                    suffix = filename.split("_", 1)[1]
                    media_data["media_path"] = (
                        f"{core_config.ACTIVITY_MEDIA_DIR}/{new_activity_id}_{suffix}"
                    )

                media_item = activity_media_schema.ActivityMedia(**media_data)
                media.append(media_item)

            if media:
                activity_media_crud.create_activity_medias(
                    media, new_activity_id, self.db
                )
                self.counts["activity_media"] += len(media)

        # Import exercise titles
        if activity_exercise_titles_data:
            titles = []
            exercise_titles_for_activity = [
                title
                for title in activity_exercise_titles_data
                if title.get("activity_id") == original_activity_id
            ]
            for title_data in exercise_titles_for_activity:
                title_data.pop("id", None)
                title_data["activity_id"] = new_activity_id
                title = activity_exercise_titles_schema.ActivityExerciseTitles(
                    **title_data
                )
                titles.append(title)

            if titles:
                activity_exercise_titles_crud.create_activity_exercise_titles(
                    titles, self.db
                )
                self.counts["activity_exercise_titles"] += len(titles)

    async def collect_and_import_activities_data_batched(
        self,
        zipf: zipfile.ZipFile,
        file_list: set[str],
        gears_id_mapping: dict[int, int],
        start_time: float,
        timeout_seconds: int,
    ) -> dict[int, int]:
        """
        Import activities in batches to manage memory.

        Args:
            zipf: ZipFile instance to read from.
            file_list: Set of file paths in ZIP.
            gears_id_mapping: Mapping of old to new gear IDs.
            start_time: Import operation start time.
            timeout_seconds: Timeout limit in seconds.

        Returns:
            Dictionary mapping old activity IDs to new IDs.

        Raises:
            ActivityLimitError: If too many activities.
            ImportTimeoutError: If operation times out.
        """
        activities_id_mapping = {}

        # Load activities list
        activities_data = self._load_single_json(zipf, "data/activities.json")
        if not activities_data:
            core_logger.print_to_log("No activities data to import", "info")
            return activities_id_mapping

        # Check activity count limit
        if len(activities_data) > self.performance_config.max_activities:
            raise ActivityLimitError(
                f"Too many activities ({len(activities_data)}). "
                f"Maximum allowed: {self.performance_config.max_activities}"
            )

        # Load small component files that won't cause memory issues
        activity_workout_steps_data = self._load_single_json(
            zipf, "data/activity_workout_steps.json", check_memory=False
        )
        activity_media_data = self._load_single_json(
            zipf, "data/activity_media.json", check_memory=False
        )
        activity_exercise_titles_data = self._load_single_json(
            zipf, "data/activity_exercise_titles.json", check_memory=False
        )

        # Get list of split files for large components
        laps_files = self._get_split_files_list(file_list, "data/activity_laps")
        sets_files = self._get_split_files_list(file_list, "data/activity_sets")
        streams_files = self._get_split_files_list(file_list, "data/activity_streams")

        core_logger.print_to_log(
            f"Importing {len(activities_data)} activities with batched component loading",
            "info",
        )

        # Process activities in batches
        batch_size = self.performance_config.batch_size
        for batch_start in range(0, len(activities_data), batch_size):
            profile_utils.check_timeout(
                timeout_seconds, start_time, ImportTimeoutError, "Import"
            )

            batch_end = min(batch_start + batch_size, len(activities_data))
            activities_batch = activities_data[batch_start:batch_end]

            core_logger.print_to_log(
                f"Processing activities batch {batch_start//batch_size + 1}: "
                f"activities {batch_start}-{batch_end}",
                "info",
            )

            # Load components for this batch only
            batch_laps = self._load_components_for_batch(
                zipf, laps_files, activities_batch, "laps"
            )
            batch_sets = self._load_components_for_batch(
                zipf, sets_files, activities_batch, "sets"
            )
            batch_streams = self._load_components_for_batch(
                zipf, streams_files, activities_batch, "streams"
            )

            # Import activities in this batch
            for activity_data in activities_batch:
                activity_data["user_id"] = self.user_id
                activity_data["gear_id"] = (
                    gears_id_mapping.get(activity_data["gear_id"])
                    if activity_data.get("gear_id") in gears_id_mapping
                    else None
                )

                original_activity_id = activity_data.get("id")
                activity_data.pop("id", None)

                activity = activity_schema.Activity(**activity_data)
                new_activity = await activities_crud.create_activity(
                    activity, self.websocket_manager, self.db, False
                )

                if original_activity_id is not None and new_activity.id is not None:
                    activities_id_mapping[original_activity_id] = new_activity.id

                    # Import activity components using batch-loaded data
                    await self.collect_and_import_activity_components(
                        batch_laps,
                        batch_sets,
                        batch_streams,
                        activity_workout_steps_data,
                        activity_media_data,
                        activity_exercise_titles_data,
                        original_activity_id,
                        new_activity.id,
                    )

                self.counts["activities"] += 1

            # Clear batch data from memory
            del batch_laps, batch_sets, batch_streams
            profile_utils.check_memory_usage(
                f"activities batch {batch_start//batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

        core_logger.print_to_log(
            f"Imported {self.counts['activities']} activities", "info"
        )
        return activities_id_mapping

    def _get_split_files_list(
        self, file_list: set[str], base_filename: str
    ) -> list[str]:
        """
        Get list of split component files from ZIP.

        Args:
            file_list: Set of all file paths in ZIP.
            base_filename: Base filename without extension.

        Returns:
            Sorted list of matching file paths.
        """
        split_files = sorted(
            [
                f
                for f in file_list
                if f.startswith(f"{base_filename}_") and f.endswith(".json")
            ]
        )
        if split_files:
            return split_files
        # Fall back to single file if no split files found
        single_file = f"{base_filename}.json"
        if single_file in file_list:
            return [single_file]
        return []

    def _load_components_for_batch(
        self,
        zipf: zipfile.ZipFile,
        component_files: list[str],
        activities_batch: list[Any],
        component_name: str,
    ) -> list[Any]:
        """
        Load components only for activities in current batch.

        Args:
            zipf: ZipFile instance to read from.
            component_files: List of component file paths.
            activities_batch: Activities in current batch.
            component_name: Name of component type.

        Returns:
            List of component data for batch activities.
        """
        if not component_files:
            return []

        # Get activity IDs in this batch
        batch_activity_ids = set(
            activity.get("id")
            for activity in activities_batch
            if activity.get("id") is not None
        )

        all_components = []

        # Load and filter components from each file
        for filename in component_files:
            try:
                components = json.loads(zipf.read(filename))
                # Only keep components for activities in this batch
                filtered = [
                    comp
                    for comp in components
                    if comp.get("activity_id") in batch_activity_ids
                ]
                all_components.extend(filtered)

                if filtered:
                    core_logger.print_to_log(
                        f"Loaded {len(filtered)}/{len(components)} {component_name} "
                        f"from {filename} for batch",
                        "debug",
                    )
            except json.JSONDecodeError as err:
                core_logger.print_to_log(
                    f"Failed to parse {filename}: {err}", "warning"
                )
            except Exception as err:
                core_logger.print_to_log(f"Error loading {filename}: {err}", "warning")

        return all_components

    async def collect_and_import_notifications_data(
        self, notifications_data: list[Any]
    ) -> None:
        if not notifications_data:
            core_logger.print_to_log("No notifications data to import", "info")
            return

        for notification_data in notifications_data:
            notification_data["user_id"] = self.user_id
            notification_data.pop("id", None)

            notification = notifications_schema.Notification(**notification_data)
            notifications_crud.create_notification(notification, self.db)
            self.counts["notifications"] += 1

        core_logger.print_to_log(
            f"Imported {self.counts['notifications']} notifications", "info"
        )

    async def collect_and_import_health_weight(
        self, health_weight_data: list[Any], health_targets_data: list[Any]
    ) -> None:
        """
        Import health data and targets.

        Args:
            health_weight_data: List of health data records.
            health_targets_data: List of health target records.
        """
        # Import health data
        if health_weight_data:
            for health_weight in health_weight_data:
                health_weight["user_id"] = self.user_id
                health_weight.pop("id", None)

                data = health_weight_schema.HealthWeightCreate(**health_weight)
                health_weight_crud.create_health_weight(self.user_id, data, self.db)
                self.counts["health_weight"] += 1
            core_logger.print_to_log(
                f"Imported {self.counts['health_weight']} health weight records", "info"
            )
        else:
            core_logger.print_to_log(f"No health weight data to import", "debug")

        # Import health targets
        if health_targets_data:
            for target_data in health_targets_data:
                current_health_target = (
                    health_targets_crud.get_health_targets_by_user_id(
                        self.user_id, self.db
                    )
                )

                target_data["user_id"] = self.user_id
                if current_health_target is not None:
                    target_data["id"] = current_health_target.id
                else:
                    target_data.pop("id", None)

                target = health_targets_schema.HealthTargetsUpdate(**target_data)
                health_targets_crud.edit_health_target(target, self.user_id, self.db)
                self.counts["health_targets"] += 1
            core_logger.print_to_log(
                f"Imported {self.counts['health_targets']} health targets", "info"
            )
        else:
            core_logger.print_to_log(f"No health targets to import", "debug")

    async def add_activity_files_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
        activities_id_mapping: dict[int, int],
    ) -> None:
        """
        Extract and import activity files from ZIP.

        Args:
            zipf: ZipFile instance to read from.
            file_list: Set of file paths in ZIP.
            activities_id_mapping: Mapping of old to new IDs.
        """
        profile_utils.check_memory_usage(
            "activity files import",
            self.performance_config.max_memory_mb,
            self.performance_config.enable_memory_monitoring,
        )

        for file_path in file_list:
            path = file_path.replace("\\", "/")

            # Import activity files
            if path.lower().endswith((".gpx", ".fit", ".tcx")) and path.startswith(
                "activity_files/"
            ):
                file_id_str = os.path.splitext(os.path.basename(path))[0]
                ext = os.path.splitext(path)[1]
                try:
                    file_id_int = int(file_id_str)
                    new_id = activities_id_mapping.get(file_id_int)

                    if new_id is None:
                        continue

                    new_file_name = f"{new_id}{ext}"
                    activity_file_path = os.path.join(
                        core_config.FILES_PROCESSED_DIR, new_file_name
                    )

                    with open(activity_file_path, "wb") as f:
                        f.write(zipf.read(file_path))
                    self.counts["activity_files"] += 1
                except ValueError:
                    # Skip files that don't have numeric activity IDs
                    continue

    async def add_activity_media_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
        activities_id_mapping: dict[int, int],
    ) -> None:
        """
        Extract and import activity media from ZIP.

        Args:
            zipf: ZipFile instance to read from.
            file_list: Set of file paths in ZIP.
            activities_id_mapping: Mapping of old to new IDs.
        """
        profile_utils.check_memory_usage(
            "activity media import",
            self.performance_config.max_memory_mb,
            self.performance_config.enable_memory_monitoring,
        )

        for file_path in file_list:
            path = file_path.replace("\\", "/")

            # Import activity media
            if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith(
                "activity_media/"
            ):
                file_name = os.path.basename(path)
                base_name, ext = os.path.splitext(file_name)

                if "_" in base_name:
                    orig_id_str, suffix = base_name.split("_", 1)
                    try:
                        orig_id_int = int(orig_id_str)
                        new_id = activities_id_mapping.get(orig_id_int)

                        if new_id is None:
                            continue

                        new_file_name = f"{new_id}_{suffix}{ext}"
                        activity_media_path = os.path.join(
                            core_config.ACTIVITY_MEDIA_DIR, new_file_name
                        )

                        with open(activity_media_path, "wb") as f:
                            f.write(zipf.read(file_path))
                        self.counts["media"] += 1
                    except ValueError:
                        # Skip files that don't have numeric activity IDs
                        continue

    async def add_user_images_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
    ) -> None:
        """
        Extract and import user images from ZIP.

        Args:
            zipf: ZipFile instance to read from.
            file_list: Set of file paths in ZIP.
        """
        profile_utils.check_memory_usage(
            "user images import",
            self.performance_config.max_memory_mb,
            self.performance_config.enable_memory_monitoring,
        )

        for file_path in file_list:
            path = file_path.replace("\\", "/")

            # Import user images
            if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith(
                "user_images/"
            ):
                ext = os.path.splitext(path)[1]
                new_file_name = f"{self.user_id}{ext}"
                user_img = os.path.join(core_config.USER_IMAGES_DIR, new_file_name)

                with open(user_img, "wb") as f:
                    f.write(zipf.read(file_path))
                self.counts["user_images"] += 1
