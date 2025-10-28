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

import users.user_integrations.crud as user_integrations_crud
import users.user_integrations.schema as users_integrations_schema

import users.user_default_gear.crud as user_default_gear_crud
import users.user_default_gear.schema as user_default_gear_schema

import users.user_goals.crud as user_goals_crud
import users.user_goals.schema as user_goals_schema

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

import health_data.crud as health_data_crud
import health_data.schema as health_data_schema

import health_targets.crud as health_targets_crud
import health_targets.schema as health_targets_schema

import websocket.schema as websocket_schema


class ImportPerformanceConfig(profile_utils.BasePerformanceConfig):
    """
    Configuration class for managing import performance parameters.

    This class extends profile_utils.BasePerformanceConfig with import-specific settings including
    file size constraints and activity limits. It provides optimized configuration
    based on system memory detection for import operations.

    Import-Specific Attributes:
        max_file_size_mb (int): Maximum allowed file size in megabytes. Default: 1000
        max_activities (int): Maximum number of activities to process. Default: 10000

    Inherited Attributes:
        batch_size (int): Number of records to process in a single batch. Default: 1000
        max_memory_mb (int): Maximum memory usage limit in megabytes. Default: 1024
        timeout_seconds (int): Operation timeout in seconds. Default: 3600 (60 minutes)
        chunk_size (int): Size of data chunks for reading/writing. Default: 8192
        enable_memory_monitoring (bool): Whether to enable memory monitoring. Default: True

    Memory Tier Configurations:
        High (>2GB): batch_size=2000, max_memory_mb=2048, timeout_seconds=7200
        Medium (>1GB): batch_size=1000, max_memory_mb=1024, timeout_seconds=3600
        Low (≤1GB): batch_size=500, max_memory_mb=512, timeout_seconds=1800
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_memory_mb: int = 1024,
        max_file_size_mb: int = 1000,
        max_activities: int = 10000,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        """
        Initialize the import performance configuration.

        Args:
            batch_size (int): Number of activities to process in a single batch. Defaults to 1000.
            max_memory_mb (int): Maximum memory usage allowed in megabytes. Defaults to 1024.
            max_file_size_mb (int): Maximum file size allowed for import in megabytes. Defaults to 1000.
            max_activities (int): Maximum number of activities that can be imported. Defaults to 10000.
            timeout_seconds (int): Maximum time allowed for import operation in seconds. Defaults to 3600.
            chunk_size (int): Size of chunks for file reading/processing in bytes. Defaults to 8192.
            enable_memory_monitoring (bool): Whether to enable memory usage monitoring. Defaults to True.
        """
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
        Get import-specific tier-based configuration mappings.

        Returns:
            dict[str, dict[str, Any]]: Mapping of memory tiers to import configuration dictionaries
        """
        return {
            "high": {
                "batch_size": 500,
                "max_memory_mb": 2048,
                "max_file_size_mb": 2000,
                "max_activities": 20000,
                "timeout_seconds": 7200,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "medium": {
                "batch_size": 250,
                "max_memory_mb": 1024,
                "max_file_size_mb": 1000,
                "max_activities": 10000,
                "timeout_seconds": 3600,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "low": {
                "batch_size": 125,
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
    Service class for importing user data from ZIP archives containing activities, gear, health information, and media files.

    This class handles the processing and import of comprehensive user data from exported ZIP files.
    It provides methods for batched data processing to optimize memory usage, with configurable
    performance settings for handling large datasets efficiently.

    The import process includes:
    - Validation of ZIP file structure and content
    - User profile data and settings
    - Gears and gear components
    - Activities and their related components (laps, sets, streams, workout steps, media)
    - Health data and targets
    - Activity files and media files
    - User profile images

    Attributes:
        user_id (int): The ID of the user for whom data is being imported.
        db (Session): SQLAlchemy database session for data persistence.
        websocket_manager: WebSocket manager for progress notifications.
        counts (dict[str, int]): Dictionary tracking the count of each imported data type.
        performance_config (ImportPerformanceConfig): Configuration settings for performance
            optimization including batch size, memory limits, and timeouts.

    Example:
        >>> from sqlalchemy.orm import Session
        >>> db = Session()
        >>> import_service = ImportService(user_id=123, db=db, websocket_manager=ws_manager)
        >>> with open('export.zip', 'rb') as f:
        ...     result = await import_service.import_from_zip_data(f.read())

    Features:
        - Uses batched processing to minimize memory usage during data import
        - Implements memory monitoring with configurable thresholds
        - Provides graceful error handling with detailed logging
        - Supports timeout enforcement for long-running operations
        - Maintains data integrity through proper ID mapping and validation
    """

    def __init__(
        self,
        user_id: int,
        db: Session,
        websocket_manager: websocket_schema.WebSocketManager,
        performance_config: ImportPerformanceConfig | None = None,
    ):
        """
        Initialize the ImportService with user context and configuration.

        Args:
            user_id (int): The ID of the user performing the import.
            db (Session): Database session for performing database operations.
            websocket_manager (websocket_schema.WebSocketManager): Manager for handling WebSocket connections and messaging.
            performance_config (ImportPerformanceConfig | None, optional): Configuration for import performance settings
                including batch size and memory limits. If None, uses auto-detected configuration. Defaults to None.

        Attributes:
            user_id (int): Stored user ID.
            db (Session): Stored database session.
            websocket_manager (websocket_schema.WebSocketManager): Stored WebSocket manager.
            counts (dict): Initialized counter dictionary for tracking import statistics.
            performance_config (ImportPerformanceConfig): Performance configuration settings for the import process.
        """
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
        Import user data from a ZIP archive containing JSON files and media.

        This method orchestrates the complete import process from a ZIP file using a
        streaming approach that loads one data type at a time to minimize memory usage.

        Process includes:
        - Validation of file size against configured limits
        - Early memory check before loading any data
        - Sequential loading and import of data in dependency order
        - Creation of ID mappings to maintain relationships between entities
        - Explicit memory cleanup between data types

        Args:
            zip_data (bytes): The ZIP file contents as bytes

        Returns:
            dict[str, Any]: A dictionary containing:
                - detail (str): Success message
                - imported (dict): Counts of imported items by type

        Raises:
            FileSizeError: If the ZIP file size exceeds the maximum allowed size
            FileFormatError: If the provided data is not a valid ZIP file
            ImportTimeoutError: If the operation exceeds timeout limits
            MemoryError: If memory usage exceeds configured limits

        Note:
            The import follows a strict dependency order to ensure referential integrity:
            1. Gears (independent)
            2. Gear components (depends on gears)
            3. User data (depends on gears)
            4. Activities (depends on gears)
            5. Health data (independent)
            6. Files and media (depends on activities)

            Uses streaming to load one data type at a time, freeing memory between steps.
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
                user_integrations_data = self._load_single_json(
                    zipf, "data/user_integrations.json"
                )
                user_goals_data = self._load_single_json(zipf, "data/user_goals.json")
                user_privacy_settings_data = self._load_single_json(
                    zipf, "data/user_privacy_settings.json"
                )

                await self.collect_and_import_user_data(
                    user_data,
                    user_default_gear_data,
                    user_integrations_data,
                    user_goals_data,
                    user_privacy_settings_data,
                    gears_id_mapping,
                )
                del user_data, user_default_gear_data, user_integrations_data
                del user_goals_data, user_privacy_settings_data

                # Load and import activities with their components
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                activities_data = self._load_single_json(zipf, "data/activities.json")

                # Load activity component data
                activity_laps_data = self._load_single_json(
                    zipf, "data/activity_laps.json"
                )
                activity_sets_data = self._load_single_json(
                    zipf, "data/activity_sets.json"
                )
                activity_streams_data = self._load_single_json(
                    zipf, "data/activity_streams.json"
                )
                activity_workout_steps_data = self._load_single_json(
                    zipf, "data/activity_workout_steps.json"
                )
                activity_media_data = self._load_single_json(
                    zipf, "data/activity_media.json"
                )
                activity_exercise_titles_data = self._load_single_json(
                    zipf, "data/activity_exercise_titles.json"
                )

                activities_id_mapping = await self.collect_and_import_activities_data(
                    activities_data,
                    activity_laps_data,
                    activity_sets_data,
                    activity_streams_data,
                    activity_workout_steps_data,
                    activity_media_data,
                    activity_exercise_titles_data,
                    gears_id_mapping,
                )
                del activities_data, activity_laps_data, activity_sets_data
                del activity_streams_data, activity_workout_steps_data
                del activity_media_data, activity_exercise_titles_data

                # Load and import health data
                profile_utils.check_timeout(
                    timeout_seconds, start_time, ImportTimeoutError, "Import"
                )
                health_data_data = self._load_single_json(zipf, "data/health_data.json")
                health_targets_data = self._load_single_json(
                    zipf, "data/health_targets.json"
                )

                await self.collect_and_import_health_data(
                    health_data_data, health_targets_data
                )
                del health_data_data, health_targets_data

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
        Load a single JSON file from the ZIP archive with optional memory checking.

        This method provides memory-efficient loading of individual JSON files,
        with optional memory usage validation after loading to prevent memory
        exhaustion during large imports.

        Args:
            zipf (zipfile.ZipFile): An opened ZipFile object to read from.
            filename (str): The path to the JSON file within the ZIP archive.
            check_memory (bool): Whether to check memory usage after loading. Defaults to True.

        Returns:
            list[Any]: The parsed JSON data as a list. Returns empty list if file not found.

        Raises:
            JSONParseError: If JSON parsing fails for the file.
            MemoryError: If memory usage exceeds configured limits after loading.

        Note:
            - Missing files return empty lists without error
            - Memory check happens after loading if check_memory is True
            - Logs the number of items loaded from each file
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
        Import gear data and create new gear records.

        This method processes gear data from an import file, creates new gear records in the database,
        and maintains a mapping between original gear IDs and newly created gear IDs for reference
        by other import operations.

        Args:
            gears_data (list[Any]): List of gear dictionaries to import.

        Returns:
            dict[int, int]: A mapping dictionary where keys are original gear IDs from the import
                           data and values are the newly created gear IDs in the database.

        Side Effects:
            - Removes original 'id' field from gear data
            - Sets 'user_id' field to the current user's ID
            - Creates new gear records in the database via gear_crud
            - Updates self.counts["gears"] counter
            - Logs the number of imported gears

        Note:
            Returns an empty dictionary if no gear data is present.
        """
        gears_id_mapping = {}

        if not gears_data:
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
        Import gear component data into the database.

        This method processes gear component records, maps their gear IDs to newly created
        gear IDs, and creates new gear component entries in the database.

        Args:
            gear_components_data (list[Any]): List of gear component records to import.
            gears_id_mapping (dict[int, int]): A dictionary mapping original gear IDs to their
                newly created gear IDs in the database. Used to map gear_id references in
                components to the new gear IDs.

        Returns:
            None

        Side Effects:
            - Creates new gear component records in the database
            - Increments the "gear_components" counter in self.counts
            - Logs the number of imported gear components

        Notes:
            - Returns early if no gear component data is present
            - Assigns the current user_id to each gear component
            - Removes the original "id" field before creating new records
            - Handles cases where gear_id mapping doesn't exist by setting it to None
            - Gear component IDs are NOT tracked in the mapping since they are not
              referenced by other entities
        """
        if not gear_components_data:
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
        user_integrations_data: list[Any],
        user_goals_data: list[Any],
        user_privacy_settings_data: list[Any],
        gears_id_mapping: dict[int, int],
    ) -> None:
        """Import user profile data and related settings.

        This method handles the import of user profile information, including profile data,
        photo paths, and delegates to specialized methods for importing user-related settings
        such as default gear, integrations, goals, and privacy settings.

        Args:
            user_data (list[Any]): List containing user profile data (expected to have one record).
            user_default_gear_data (list[Any]): List containing user default gear settings.
            user_integrations_data (list[Any]): List containing user integration settings.
            user_goals_data (list[Any]): List containing user goals.
            user_privacy_settings_data (list[Any]): List containing user privacy settings.
            gears_id_mapping (dict[int, int]): Mapping of old gear IDs to new gear IDs for
                maintaining references after import.

        Returns:
            None

        Side Effects:
            - Updates the user profile in the database with the imported data
            - Modifies photo_path to match the current user_id if applicable
            - Increments the user count in self.counts
            - Triggers imports of user default gear, integrations, goals, and privacy settings

        Note:
            - If user_data is empty or None, the method returns early without processing
            - Photo paths are renamed to use the current user_id while preserving the file extension
            - Only processes the first user data record from the list
        """
        if not user_data:
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
        await self.collect_and_import_user_integrations(user_integrations_data)
        await self.collect_and_import_user_goals(user_goals_data)
        await self.collect_and_import_user_privacy_settings(user_privacy_settings_data)

    async def collect_and_import_user_default_gear(
        self, user_default_gear_data: list[Any], gears_id_mapping: dict[int, int]
    ) -> None:
        """
        Import and update user's default gear settings for various activity types.

        This method processes the user's default gear data from an import file and updates
        the existing user's default gear settings in the database. It maps old gear IDs to
        new gear IDs using the provided mapping dictionary.

        Args:
            user_default_gear_data (list[Any]): List containing user's default gear configuration.
            gears_id_mapping (dict[int, int]): Mapping of old gear IDs to new gear IDs
                for translating gear references during import.

        Returns:
            None

        Raises:
            None explicitly, but may raise database-related exceptions from CRUD operations.

        Side Effects:
            - Updates the user's default gear settings in the database
            - Increments the 'user_default_gear' counter in self.counts
            - If an old gear ID is not found in the mapping, sets the field to None

        Note:
            - If no user_default_gear_data is present, the method returns early
            - The method processes multiple gear fields for different activity types
              (running, cycling, swimming, skiing, etc.)
            - Uses the existing user's default gear ID to maintain database consistency
        """
        if not user_default_gear_data:
            return

        current_user_default_gear = (
            user_default_gear_crud.get_user_default_gear_by_user_id(
                self.user_id, self.db
            )
        )

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
        ]

        for field in gear_fields:
            old_gear_id = gear_data.get(field)
            if old_gear_id in gears_id_mapping:
                gear_data[field] = gears_id_mapping[old_gear_id]
            else:
                gear_data[field] = None

        user_default_gear = user_default_gear_schema.UserDefaultGear(**gear_data)
        user_default_gear_crud.edit_user_default_gear(
            user_default_gear, self.user_id, self.db
        )
        self.counts["user_default_gear"] += 1

    async def collect_and_import_user_integrations(
        self, user_integrations_data: list[Any]
    ) -> None:
        """
        Import and update user integrations from the imported data.

        This method processes user integration data from the import and updates
        the existing user integrations in the database. It retrieves the current user
        integrations, updates them with the imported data while preserving the existing
        ID and user_id, and then persists the changes.

        Args:
            user_integrations_data (list[Any]): List containing the integration data to import.

        Returns:
            None

        Note:
            - If no user_integrations_data is present, the method returns early.
            - The method assumes only one set of integration data per user (uses index [0]).
            - Increments the 'user_integrations' counter in self.counts upon successful import.
            - The existing integration ID and user_id are preserved during the update.
        """
        if not user_integrations_data:
            return

        current_user_integrations = (
            user_integrations_crud.get_user_integrations_by_user_id(
                self.user_id, self.db
            )
        )

        integrations_data = user_integrations_data[0]
        integrations_data["id"] = current_user_integrations.id
        integrations_data["user_id"] = self.user_id

        user_integrations = users_integrations_schema.UsersIntegrations(
            **integrations_data
        )
        user_integrations_crud.edit_user_integrations(
            user_integrations, self.user_id, self.db
        )
        self.counts["user_integrations"] += 1

    async def collect_and_import_user_goals(self, user_goals_data: list[Any]) -> None:
        """
        Import user goals from the data list.

        This method processes the user goals data and creates new goal records for the
        current user. It removes the 'id' and 'user_id' fields from each goal to ensure
        new records are created rather than attempting to update existing ones.

        Args:
            user_goals_data (list[Any]): List of goal data dictionaries to import.

        Returns:
            None

        Raises:
            None explicitly, but may raise database-related exceptions from
            user_goals_crud.create_user_goal().

        Note:
            - If user_goals_data is empty or None, the method returns early.
            - Each successfully imported goal increments the 'user_goals' counter
              in self.counts.
            - The method uses self.user_id and self.db which should be instance
              attributes.
        """
        if not user_goals_data:
            return

        for goal_data in user_goals_data:
            goal_data.pop("id", None)
            goal_data.pop("user_id", None)

            goal = user_goals_schema.UserGoalCreate(**goal_data)
            user_goals_crud.create_user_goal(self.user_id, goal, self.db)
            self.counts["user_goals"] += 1

    async def collect_and_import_user_privacy_settings(
        self, user_privacy_settings_data: list[Any]
    ) -> None:
        """
        Import and update user privacy settings from backup data.

        This method imports user privacy settings from the backup data and updates
        the existing privacy settings for the current user. It preserves the current
        user's ID and privacy settings ID while applying the imported configuration.

        Args:
            user_privacy_settings_data (list[Any]): List containing privacy settings data.
                Expected structure: [dict, ...]

        Returns:
            None

        Raises:
            May raise database-related exceptions from the CRUD operations.

        Note:
            - If no privacy settings data exists, the method returns early
            - Increments the 'user_privacy_settings' counter in self.counts upon success
            - The imported settings are merged with the current user's ID and settings ID
        """
        if not user_privacy_settings_data:
            return

        current_user_privacy_settings = (
            users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                self.user_id, self.db
            )
        )

        privacy_data = user_privacy_settings_data[0]
        privacy_data["id"] = current_user_privacy_settings.id
        privacy_data["user_id"] = self.user_id

        user_privacy_settings = users_privacy_settings_schema.UsersPrivacySettings(
            **privacy_data
        )
        users_privacy_settings_crud.edit_user_privacy_settings(
            self.user_id, user_privacy_settings, self.db
        )
        self.counts["user_privacy_settings"] += 1

    async def collect_and_import_activities_data(
        self,
        activities_data: list[Any],
        activity_laps_data: list[Any],
        activity_sets_data: list[Any],
        activity_streams_data: list[Any],
        activity_workout_steps_data: list[Any],
        activity_media_data: list[Any],
        activity_exercise_titles_data: list[Any],
        gears_id_mapping: dict[int, int],
    ) -> dict[int, int]:
        """
        Import activities data and their components into the database.

        This method processes activity data from an import file, validates activity count limits,
        maps gear IDs to newly created gears, creates new activity records in the database,
        and imports associated activity components.

        Args:
            activities_data (list[Any]): List of activity records to import.
            activity_laps_data (list[Any]): List of lap records for all activities.
            activity_sets_data (list[Any]): List of set records for all activities.
            activity_streams_data (list[Any]): List of stream records for all activities.
            activity_workout_steps_data (list[Any]): List of workout step records.
            activity_media_data (list[Any]): List of media records for activities.
            activity_exercise_titles_data (list[Any]): List of exercise title records.
            gears_id_mapping (dict[int, int]): Mapping of original gear IDs to newly created
                gear IDs in the database.

        Returns:
            dict[int, int]: Mapping of original activity IDs to newly created activity IDs
                in the database. This mapping is used to link related data like streams
                and laps to the correct activities.

        Raises:
            ActivityLimitError: If the number of activities exceeds the configured maximum limit.

        Side Effects:
            - Creates new activity records in the database
            - Imports activity components for each created activity
            - Increments the activity count in self.counts["activities"]
            - Logs the total number of imported activities

        Note:
            - Activity IDs are remapped to avoid conflicts with existing records
            - Activities are associated with the current user (self.user_id)
            - Gear IDs are remapped using the provided gears_id_mapping
            - Returns an empty mapping if no activities data is present
            - Large data (laps, sets, streams) are passed as dictionaries grouped by activity_id for memory efficiency
        """
        activities_id_mapping = {}

        if not activities_data:
            return activities_id_mapping

        # Check activity count limit
        if len(activities_data) > self.performance_config.max_activities:
            raise ActivityLimitError(
                f"Too many activities ({len(activities_data)}). "
                f"Maximum allowed: {self.performance_config.max_activities}"
            )

        for activity_data in activities_data:
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
                # Import activity components - pass full lists, will filter inside
                await self.collect_and_import_activity_components(
                    activity_laps_data,
                    activity_sets_data,
                    activity_streams_data,
                    activity_workout_steps_data,
                    activity_media_data,
                    activity_exercise_titles_data,
                    original_activity_id,
                    new_activity.id,
                )

            self.counts["activities"] += 1

        core_logger.print_to_log(
            f"Imported {self.counts['activities']} activities", "info"
        )
        return activities_id_mapping

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
        Import all activity-related components for a newly created activity.

        This method handles the import of various activity components including laps, sets,
        streams, workout steps, media files, and exercise titles. Each component is filtered
        by the original activity ID, updated with the new activity ID, and then created in
        the database. The method also maintains counts of imported items.

        Args:
            activity_laps_data (list[Any]): List of lap records
            activity_sets_data (list[Any]): List of set records
            activity_streams_data (list[Any]): List of stream records
            activity_workout_steps_data (list[Any]): List of workout step records
            activity_media_data (list[Any]): List of media records
            activity_exercise_titles_data (list[Any]): List of exercise title records
            original_activity_id (int): The activity ID from the original/exported data
            new_activity_id (int): The newly created activity ID in the target database

        Returns:
            None

        Side Effects:
            - Creates multiple database records for activity components
            - Updates self.counts dictionary with imported item counts
            - Updates media file paths to reference the new activity ID

        Note:
            All original IDs are removed from the component data before creating new records
            to allow the database to assign new IDs automatically.
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

    async def collect_and_import_health_data(
        self, health_data_data: list[Any], health_targets_data: list[Any]
    ) -> None:
        """
        Import health data and health targets for a user.

        This method processes and imports health data records and health targets from the
        provided data lists into the database for the specified user.

        Args:
            health_data_data (list[Any]): List of health data records to import
            health_targets_data (list[Any]): List of health target records to import

        Returns:
            None

        Side Effects:
            - Creates new health data records in the database
            - Updates or creates health target records in the database
            - Updates self.counts dictionary with the number of imported records

        Note:
            - Each health data record has its 'id' field removed and 'user_id' set to self.user_id
            - Health targets are either updated (if existing) or created (if new)
            - The method modifies the input data dictionaries in place
        """
        # Import health data
        if health_data_data:
            for health_data in health_data_data:
                health_data["user_id"] = self.user_id
                health_data.pop("id", None)

                data = health_data_schema.HealthData(**health_data)
                health_data_crud.create_health_data(self.user_id, data, self.db)
                self.counts["health_data"] += 1

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

                target = health_targets_schema.HealthTargets(**target_data)
                health_targets_crud.edit_health_target(target, self.user_id, self.db)
                self.counts["health_targets"] += 1

    async def add_activity_files_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
        activities_id_mapping: dict[int, int],
    ) -> None:
        """
        Import activity files from the ZIP archive.
        This method processes and imports activity files (GPX, FIT, TCX) from the 'activity_files/' directory
        within the ZIP archive. Files are remapped to new activity IDs based on the activities_id_mapping.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object containing the files to import.
            file_list (set): Set of file paths within the ZIP archive to process.
            activities_id_mapping (dict[int, int]): Mapping from original activity IDs to new activity IDs.

        Returns:
            None

        Side Effects:
            - Writes activity files to disk in FILES_PROCESSED_DIR
            - Updates self.counts["activity_files"] with import statistics
            - Checks memory usage before processing

        Notes:
            - Activity files are expected to be named with numeric IDs (e.g., "123.gpx")
            - Files with non-numeric activity IDs are silently skipped
            - If an activity ID is not found in activities_id_mapping, the file is skipped
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
        Import activity media files from the ZIP archive.
        This method processes and imports activity media files (PNG, JPG, JPEG) from the 'activity_media/'
        directory within the ZIP archive. Media files are remapped to new activity IDs based on the
        activities_id_mapping.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object containing the files to import.
            file_list (set): Set of file paths within the ZIP archive to process.
            activities_id_mapping (dict[int, int]): Mapping from original activity IDs to new activity IDs.

        Returns:
            None

        Side Effects:
            - Writes media files to disk in ACTIVITY_MEDIA_DIR
            - Updates self.counts["media"] with import statistics
            - Checks memory usage before processing

        Notes:
            - Activity media files are expected to follow the pattern "{activity_id}_{suffix}.{ext}"
            - Files with non-numeric activity IDs are silently skipped
            - If an activity ID is not found in activities_id_mapping, the file is skipped
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
        Import user profile images from the ZIP archive.
        This method processes and imports user profile images (PNG, JPG, JPEG) from the 'user_images/'
        directory within the ZIP archive. Images are renamed using the user_id as the base name.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object containing the files to import.
            file_list (set): Set of file paths within the ZIP archive to process.

        Returns:
            None

        Side Effects:
            - Writes user images to disk in USER_IMAGES_DIR
            - Updates self.counts["user_images"] with import statistics
            - Checks memory usage before processing

        Notes:
            - User images are renamed using the user_id as the base name while preserving the file extension
            - Only processes image files in the 'user_images/' directory
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
