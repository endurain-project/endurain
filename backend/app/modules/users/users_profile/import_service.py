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

import asyncio
import json
import os
import time
import zipfile
from io import BytesIO
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as file_uploads
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activities_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_file_storage.service as activity_file_storage_service
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema
import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.crud as user_default_gear_crud
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_goals.crud as user_goals_crud
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.schema as users_integrations_schema
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.utils as profile_utils
import modules.websocket.manager as websocket_manager
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    ImportTimeoutError,
    JSONParseError,
)

logger = core_logger.get_logger(__name__)


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
        self.counts = profile_utils.initialize_operation_counts(include_user_count=False)
        self.performance_config: ImportPerformanceConfig = (
            performance_config or ImportPerformanceConfig.get_auto_config()
        )

        logger.info(
            f"ImportService initialized with performance config: "
            f"batch_size={self.performance_config.batch_size}, "
            f"max_memory_mb={self.performance_config.max_memory_mb}, "
            f"max_file_size_mb={self.performance_config.max_file_size_mb}, "
            f"timeout_seconds={self.performance_config.timeout_seconds}"
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
                gears_id_mapping: dict[int, int] = {}
                activities_id_mapping: dict[int, int] = {}

                # Import data in dependency order using streaming approach
                # Load and import gears
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                gears_data = self._load_single_json(zipf, "data/gears.json")
                gears_id_mapping = await self.collect_and_import_gears_data(gears_data)
                del gears_data  # Explicit memory cleanup

                # Load and import gear components
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                gear_components_data = self._load_single_json(zipf, "data/gear_components.json")
                await self.collect_and_import_gear_components_data(gear_components_data, gears_id_mapping)
                del gear_components_data

                # Load and import user data (includes user, default gear, integrations, goals, privacy)
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                user_data = self._load_single_json(zipf, "data/user.json")
                user_default_gear_data = self._load_single_json(zipf, "data/user_default_gear.json")
                user_goals_data = self._load_single_json(zipf, "data/user_goals.json")
                user_integrations_data = self._load_single_json(zipf, "data/user_integrations.json")
                user_privacy_settings_data = self._load_single_json(zipf, "data/user_privacy_settings.json")

                await self.collect_and_import_user_data(
                    user_data,
                    user_default_gear_data,
                    user_goals_data,
                    user_integrations_data,
                    user_privacy_settings_data,
                    gears_id_mapping,
                )
                del user_data, user_default_gear_data, user_integrations_data
                del user_goals_data, user_privacy_settings_data

                # Load and import activities with their components
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")

                # Import activities and components using batched approach to avoid memory issues
                activities_id_mapping = await self.collect_and_import_activities_data_batched(
                    zipf,
                    file_list,
                    gears_id_mapping,
                    start_time,
                    timeout_seconds,
                )

                # Load and import health data
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                health_weight_data = self._load_single_json(zipf, "data/health_weight.json")
                health_targets_data = self._load_single_json(zipf, "data/health_targets.json")

                await self.collect_and_import_health_weight(health_weight_data, health_targets_data)
                del health_weight_data, health_targets_data

                # Import files and media
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                await self.add_activity_files_from_zip(zipf, file_list, activities_id_mapping)
                await self.add_activity_media_from_zip(zipf, file_list, activities_id_mapping)
                await self.add_user_images_from_zip(zipf, file_list)

        except zipfile.BadZipFile as e:
            raise FileFormatError(f"Invalid ZIP file format: {e!s}") from e
        except OSError as e:
            raise FileSystemError(f"File system error during import: {e!s}") from e

        # Guard: if nothing was imported, fail visibly instead of
        # returning a misleading "success" with zero counts.
        if all(v == 0 for v in self.counts.values()):
            raise FileFormatError(
                "Import completed with zero items imported. The ZIP file contains no importable data."
            )

        return {"detail": "Import completed", "imported": self.counts}

    def _load_single_json(self, zipf: zipfile.ZipFile, filename: str, check_memory: bool = True) -> list[Any]:
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
                logger.warning(f"Expected data file {filename} not found in ZIP archive")
                return []

            data = json.loads(self._read_zip_entry(zipf, filename))

            if not isinstance(data, list):
                logger.warning(f"Expected list in {filename}, got {type(data).__name__}, returning empty list")
                return []

            logger.debug(f"Loaded {len(data)} items from {filename}")

            if check_memory:
                profile_utils.check_memory_usage(
                    f"loading {filename}",
                    self.performance_config.max_memory_mb,
                    self.performance_config.enable_memory_monitoring,
                )

            return data
        except json.JSONDecodeError as err:
            error_msg = f"Failed to parse JSON from {filename}: {err}"
            logger.error(error_msg)
            raise JSONParseError(error_msg) from err

    def _read_zip_entry(
        self,
        zipf: zipfile.ZipFile,
        filename: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        """
        Read a ZIP entry after checking its declared size.

        Args:
            zipf: ZipFile instance to read from.
            filename: Name of the entry to read.
            max_bytes: Optional byte cap for this entry. Defaults
                to the import performance file-size cap.

        Returns:
            Entry bytes.

        Raises:
            FileSizeError: If the entry exceeds the allowed size.
        """
        limit = max_bytes if max_bytes is not None else self.performance_config.max_file_size_mb * 1024 * 1024
        info = zipf.getinfo(filename)
        # ``info.file_size`` comes from the central directory and a
        # malicious archive can lie. The declared-size check below
        # is a fast pre-filter; the streaming read that follows
        # enforces the same cap against the actual decompressed
        # bytes so a zip-bomb cannot exhaust memory.
        if info.file_size > limit:
            raise FileSizeError(
                f"ZIP entry {filename} size ({info.file_size} bytes) exceeds maximum allowed ({limit} bytes)"
            )
        chunks: list[bytes] = []
        bytes_read = 0
        chunk_size = 64 * 1024
        with zipf.open(info, "r") as src:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > limit:
                    raise FileSizeError(
                        f"ZIP entry {filename} decompressed size exceeds maximum allowed ({limit} bytes)"
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    async def collect_and_import_gears_data(self, gears_data: list[Any]) -> dict[int, int]:
        """
        Import gear data and create ID mappings.

        Args:
            gears_data: List of gear data dictionaries.

        Returns:
            Dictionary mapping old gear IDs to new IDs.
        """
        gears_id_mapping: dict[int, int] = {}

        if not gears_data:
            logger.info("No gears data to import")
            return gears_id_mapping

        for gear_data in gears_data:
            gear_data["user_id"] = self.user_id
            original_id = gear_data.get("id")
            gear_data.pop("id", None)

            gear = gear_schema.GearCreate(**gear_data)
            new_gear = gear_crud.create_gear(gear, self.user_id, self.db)
            gears_id_mapping[original_id] = new_gear.id
            self.counts["gears"] += 1

        logger.info(f"Imported {self.counts['gears']} gears")
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
            logger.info("No gear components data to import")
            return

        for gear_component_data in gear_components_data:
            gear_component_data["gear_id"] = (
                gears_id_mapping.get(gear_component_data["gear_id"])
                if gear_component_data.get("gear_id") in gears_id_mapping
                else None
            )

            gear_component_data.pop("id", None)

            gear_component = gear_components_schema.GearComponentCreate(**gear_component_data)
            gear_components_crud.create_gear_component(gear_component, self.user_id, self.db)
            self.counts["gear_components"] += 1

        logger.info(f"Imported {self.counts['gear_components']} gear components")

    async def collect_and_import_user_data(
        self,
        user_data: list[Any],
        user_default_gear_data: list[Any],
        user_goals_data: list[Any],
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
            user_integrations_data: Integration settings.
            user_privacy_settings_data: Privacy settings.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if user_data:
            # Import user profile
            user_profile = user_data[0]
            user_profile["id"] = self.user_id

            # Handle photo path
            photo_path = user_profile.get("photo_path")
            if isinstance(photo_path, str) and photo_path.startswith("data/user_images/"):
                extension = photo_path.split(".")[-1]
                user_profile["photo_path"] = f"data/user_images/{self.user_id}.{extension}"

            # Strict allow-list before persistence: profile import is a
            # self-service operation and MUST NOT be a back door for
            # privilege escalation. Even if the source ZIP was crafted
            # to set ``access_type``, ``active``, ``mfa_enabled``,
            # ``mfa_secret``, ``email_verified``, or
            # ``pending_admin_approval``, those fields are dropped here
            # before reaching the database.
            sanitized = {
                key: value for key, value in user_profile.items() if key in users_crud.PROFILE_SELF_SERVICE_FIELDS
            }
            profile_payload = users_schema.ProfileUpdate.model_validate(sanitized)
            await users_crud.edit_profile_user(self.user_id, profile_payload, self.db)
            self.counts["user"] += 1
        else:
            logger.info("No user data to import, but continuing with sub-settings")

        # Import user-related settings — always attempt, even if
        # user_data was empty, so that sub-setting data loaded from
        # the ZIP is not silently discarded.
        await self.collect_and_import_user_default_gear(user_default_gear_data, gears_id_mapping)
        await self.collect_and_import_user_goals(user_goals_data)
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
            logger.info("No user default gear data to import")
            return

        current_user_default_gear = user_default_gear_crud.get_user_default_gear_by_user_id(self.user_id, self.db)

        if current_user_default_gear is None:
            logger.info("No existing user default gear, creating new record")
            current_user_default_gear = user_default_gear_crud.create_user_default_gear(self.user_id, self.db)

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
            gear_data[field] = gears_id_mapping.get(old_gear_id)

        user_default_gear = user_default_gear_schema.UsersDefaultGearUpdate(**gear_data)
        user_default_gear_crud.edit_user_default_gear(user_default_gear, self.user_id, self.db)
        logger.info("Imported user default gear")
        self.counts["user_default_gear"] += 1

    async def collect_and_import_user_integrations(self, user_integrations_data: list[Any]) -> None:
        """
        Import user integration settings.

        Args:
            user_integrations_data: Integration data.
        """
        if not user_integrations_data:
            logger.info("No user integrations data to import")
            return

        integrations_data = user_integrations_data[0]
        integrations_data.pop("id", None)
        integrations_data.pop("user_id", None)

        user_integrations = users_integrations_schema.UsersIntegrationsUpdate(**integrations_data)
        user_integrations_crud.edit_user_integrations(user_integrations, self.user_id, self.db)
        logger.info("Imported user integrations")
        self.counts["user_integrations"] += 1

    async def collect_and_import_user_goals(self, user_goals_data: list[Any]) -> None:
        """
        Import user goals data.

        Args:
            user_goals_data: List of user goal dictionaries.
        """
        if not user_goals_data:
            logger.info("No user goals data to import")
            return

        for goal_data in user_goals_data:
            goal_data.pop("id", None)
            goal_data.pop("user_id", None)

            goal = user_goals_schema.UsersGoalCreate(**goal_data)
            user_goals_crud.create_user_goal(self.user_id, goal, self.db)
            self.counts["user_goals"] += 1

        logger.info(f"Imported {self.counts['user_goals']} user goals")

    async def collect_and_import_user_privacy_settings(self, user_privacy_settings_data: list[Any]) -> None:
        """
        Import user privacy settings.

        Args:
            user_privacy_settings_data: Privacy settings data.
        """
        if not user_privacy_settings_data:
            logger.info("No user privacy settings data to import")
            return

        privacy_data = user_privacy_settings_data[0]
        privacy_data.pop("id", None)
        privacy_data.pop("user_id", None)

        user_privacy_settings = users_privacy_settings_schema.UsersPrivacySettingsUpdate(**privacy_data)
        users_privacy_settings_crud.edit_user_privacy_settings(self.user_id, user_privacy_settings, self.db)
        logger.info("Imported user privacy settings")
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
        new_activity: activity_schema.Activity,
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
            new_activity: New activity object.
        """
        # Import laps - filter for this activity
        if activity_laps_data:
            laps = []
            laps_for_activity = [lap for lap in activity_laps_data if lap.get("activity_id") == original_activity_id]
            for lap_data in laps_for_activity:
                lap_data.pop("id", None)
                lap_data["activity_id"] = new_activity.id
                laps.append(lap_data)

            if laps and new_activity.id is not None:
                activity_laps_crud.create_activity_laps(laps, new_activity.id, self.db)
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
                activity_set["activity_id"] = new_activity.id
                set_activity = activity_sets_schema.ActivitySetsCreate(**activity_set)
                sets.append(set_activity)

            if sets and new_activity.id is not None:
                activity_sets_crud.create_activity_sets(list(sets), new_activity.id, self.db)
                self.counts["activity_sets"] += len(sets)

        # Import streams - filter for this activity
        if activity_streams_data:
            streams = []
            streams_for_activity = [
                stream for stream in activity_streams_data if stream.get("activity_id") == original_activity_id
            ]
            for stream_data in streams_for_activity:
                stream_data.pop("id", None)
                stream_data["activity_id"] = new_activity.id
                stream = activity_streams_schema.ActivityStreamsCreate(**stream_data)
                streams.append(stream)

            if streams:
                activity_streams_crud.create_activity_streams(streams, new_activity, self.db)
                self.counts["activity_streams"] += len(streams)

        # Import workout steps
        if activity_workout_steps_data:
            steps = []
            steps_for_activity = [
                step for step in activity_workout_steps_data if step.get("activity_id") == original_activity_id
            ]
            for step_data in steps_for_activity:
                step_data.pop("id", None)
                step_data["activity_id"] = new_activity.id
                step = activity_workout_steps_schema.ActivityWorkoutSteps(**step_data)
                steps.append(step)

            if steps and new_activity.id is not None:
                activity_workout_steps_crud.create_activity_workout_steps(steps, new_activity.id, self.db)
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
                media_data["activity_id"] = new_activity.id

                # Update media path
                old_path = media_data.get("media_path", None)
                if old_path:
                    filename = os.path.basename(str(old_path).replace("\\", "/"))
                    if "_" not in filename:
                        logger.warning(f"Skipping activity media with invalid path: {old_path}")
                        continue
                    suffix = filename.split("_", 1)[1]
                    new_file_name = f"{new_activity.id}_{suffix}"
                    try:
                        media_data["media_path"] = str(
                            file_uploads.resolve_storage_path(
                                core_config.settings.ACTIVITY_MEDIA_DIR,
                                new_file_name,
                            )
                        )
                    except HTTPException as err:
                        logger.warning(f"Skipping activity media with unsafe path {old_path}: {err.detail}")
                        continue

                media_item = activity_media_schema.ActivityMedia(**media_data)
                media.append(media_item)

            if media and new_activity.id is not None:
                activity_media_crud.create_activity_medias(media, new_activity.id, self.db)
                self.counts["activity_media"] += len(media)

        # Import exercise titles
        if activity_exercise_titles_data:
            titles = []
            exercise_titles_for_activity = [
                title for title in activity_exercise_titles_data if title.get("activity_id") == original_activity_id
            ]
            for title_data in exercise_titles_for_activity:
                title_data.pop("id", None)
                title_data["activity_id"] = new_activity.id
                title = activity_exercise_titles_schema.ActivityExerciseTitles(**title_data)
                titles.append(title)

            if titles:
                activity_exercise_titles_crud.create_activity_exercise_titles(titles, self.db)
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
        activities_id_mapping: dict[int, int] = {}

        # Load activities list
        activities_data = self._load_single_json(zipf, "data/activities.json")
        if not activities_data:
            logger.info("No activities data to import")
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
        activity_media_data = self._load_single_json(zipf, "data/activity_media.json", check_memory=False)
        activity_exercise_titles_data = self._load_single_json(
            zipf, "data/activity_exercise_titles.json", check_memory=False
        )

        # Get list of split files for large components
        laps_files = self._get_split_files_list(file_list, "data/activity_laps")
        sets_files = self._get_split_files_list(file_list, "data/activity_sets")
        streams_files = self._get_split_files_list(file_list, "data/activity_streams")

        logger.info(f"Importing {len(activities_data)} activities with batched component loading")

        # Process activities in batches
        batch_size = self.performance_config.batch_size
        for batch_start in range(0, len(activities_data), batch_size):
            profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")

            batch_end = min(batch_start + batch_size, len(activities_data))
            activities_batch = activities_data[batch_start:batch_end]

            logger.info(
                f"Processing activities batch {batch_start // batch_size + 1}: activities {batch_start}-{batch_end}"
            )

            # Load components for this batch only
            batch_laps = self._load_components_for_batch(zipf, laps_files, activities_batch, "laps")
            batch_sets = self._load_components_for_batch(zipf, sets_files, activities_batch, "sets")
            batch_streams = self._load_components_for_batch(zipf, streams_files, activities_batch, "streams")

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

                activity = activity_contracts.ActivityCore(**activity_data)
                # Bulk restore deliberately does not publish activity.created;
                # see integration_service.restore_activity for why.
                new_activity = activities_integration.restore_activity(activity, self.db)

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
                        new_activity,
                    )

                self.counts["activities"] += 1

            # Clear batch data from memory
            del batch_laps, batch_sets, batch_streams
            profile_utils.check_memory_usage(
                f"activities batch {batch_start // batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

        logger.info(f"Imported {self.counts['activities']} activities")
        return activities_id_mapping

    def _get_split_files_list(self, file_list: set[str], base_filename: str) -> list[str]:
        """
        Get list of split component files from ZIP.

        Args:
            file_list: Set of all file paths in ZIP.
            base_filename: Base filename without extension.

        Returns:
            Sorted list of matching file paths.
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
        batch_activity_ids = set(activity.get("id") for activity in activities_batch if activity.get("id") is not None)

        all_components = []

        # Load and filter components from each file
        for filename in component_files:
            try:
                components = json.loads(self._read_zip_entry(zipf, filename))
                # Only keep components for activities in this batch
                filtered = [comp for comp in components if comp.get("activity_id") in batch_activity_ids]
                all_components.extend(filtered)

                if filtered:
                    logger.debug(f"Loaded {len(filtered)}/{len(components)} {component_name} from {filename} for batch")
            except json.JSONDecodeError as err:
                logger.warning(f"Failed to parse {filename}: {err}")
            except (FileFormatError, FileSizeError, OSError) as err:
                logger.warning(f"Error loading {filename}: {err}")

        return all_components

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
                health_weight.pop("id", None)
                health_weight.pop("user_id", None)

                # Convert string numeric values to floats
                numeric_fields = [
                    "weight",
                    "bmi",
                    "body_fat",
                    "body_water",
                    "bone_mass",
                    "muscle_mass",
                    "visceral_fat",
                ]
                for field in numeric_fields:
                    if field in health_weight and isinstance(health_weight[field], str):
                        try:
                            health_weight[field] = float(health_weight[field])
                        except (ValueError, TypeError):
                            health_weight[field] = None

                # Convert integer fields
                int_fields = ["physique_rating", "metabolic_age"]
                for field in int_fields:
                    if field in health_weight and isinstance(health_weight[field], str):
                        try:
                            health_weight[field] = int(health_weight[field])
                        except (ValueError, TypeError):
                            health_weight[field] = None

                data = health_weight_schema.HealthWeightCreate(**health_weight)
                health_weight_crud.create_health_weight(self.user_id, data, self.db)
                self.counts["health_weight"] += 1
            logger.info(f"Imported {self.counts['health_weight']} health weight records")
        else:
            logger.debug("No health weight data to import")

        # Import health targets
        if health_targets_data:
            for target_data in health_targets_data:
                current_health_target = health_targets_crud.get_health_targets_by_user_id(self.user_id, self.db)

                # Convert string numeric values to floats/ints
                if isinstance(target_data.get("weight"), str):
                    try:
                        target_data["weight"] = float(target_data["weight"])
                    except (ValueError, TypeError):
                        target_data["weight"] = None

                int_fields = ["steps", "sleep"]
                for field in int_fields:
                    if isinstance(target_data.get(field), str):
                        try:
                            target_data[field] = int(target_data[field])
                        except (ValueError, TypeError):
                            target_data[field] = None

                target_data["user_id"] = self.user_id
                if current_health_target is not None:
                    target_data["id"] = current_health_target.id
                else:
                    target_data.pop("id", None)

                target = health_targets_schema.HealthTargetsUpdate(**target_data)
                health_targets_crud.edit_health_target(target, self.user_id, self.db)
                self.counts["health_targets"] += 1
            logger.info(f"Imported {self.counts['health_targets']} health targets")
        else:
            logger.debug("No health targets to import")

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
            if path.lower().endswith((".gpx", ".fit", ".tcx")) and path.startswith("activity_files/"):
                file_id_str = os.path.splitext(os.path.basename(path))[0]
                ext = os.path.splitext(path)[1]
                try:
                    file_id_int = int(file_id_str)
                    new_id = activities_id_mapping.get(file_id_int)

                    if new_id is None:
                        continue

                    new_file_name = f"{new_id}{ext}"

                    # Read bytes from ZIP, validate as an activity file, then
                    # persist through the platform StorageProvider (the same store
                    # the ingestion path writes to) rather than the local
                    # processed directory. The blocking save is offloaded so it
                    # never stalls the import's event loop.
                    activity_limit = file_uploads.file_validator.config.limits.max_activity_file_size
                    file_bytes = self._read_zip_entry(zipf, file_path, max_bytes=activity_limit)
                    try:
                        await file_uploads.validate_bytes(
                            file_bytes,
                            kind=file_uploads.UploadKind.ACTIVITY,
                            filename=new_file_name,
                        )
                    except HTTPException as err:
                        logger.warning(f"Profile import dropped invalid activity file {new_file_name}: {err.detail}")
                        continue
                    await asyncio.to_thread(
                        activity_file_storage_service.store_activity_file,
                        new_id,
                        ext,
                        file_bytes,
                        platform_runtime.get_active_platform().storage,
                    )
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
            if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith("activity_media/"):
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

                        # Read bytes from ZIP and save through the
                        # unified validated-write pipeline so the
                        # entry is re-checked as an image.
                        image_limit = file_uploads.file_validator.config.limits.max_image_size
                        file_bytes = self._read_zip_entry(zipf, file_path, max_bytes=image_limit)
                        try:
                            await file_uploads.save_validated_bytes(
                                file_bytes,
                                kind=file_uploads.UploadKind.IMAGE,
                                upload_dir=(core_config.settings.ACTIVITY_MEDIA_DIR),
                                filename=new_file_name,
                            )
                        except HTTPException as err:
                            logger.warning(
                                f"Profile import dropped invalid activity media {new_file_name}: {err.detail}"
                            )
                            continue
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
            if path.lower().endswith((".png", ".jpg", ".jpeg")) and path.startswith("user_images/"):
                logger.debug(f"Processing user image file: {file_path}")
                ext = os.path.splitext(path)[1]
                new_file_name = f"{self.user_id}{ext}"

                # Read bytes from ZIP and save through the unified
                # validated-write pipeline so the entry is re-checked
                # as an image.
                image_limit = file_uploads.file_validator.config.limits.max_image_size
                file_bytes = self._read_zip_entry(zipf, file_path, max_bytes=image_limit)
                try:
                    await file_uploads.save_validated_bytes(
                        file_bytes,
                        kind=file_uploads.UploadKind.IMAGE,
                        upload_dir=core_config.USER_IMAGES_DIR,
                        filename=new_file_name,
                    )
                except HTTPException as err:
                    logger.warning(f"Profile import dropped invalid user image {new_file_name}: {err.detail}")
                    continue
                self.counts["user_images"] += 1
