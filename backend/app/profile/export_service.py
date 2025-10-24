import os
import tempfile
import zipfile
import time
from typing import Generator, Dict, Any, List
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
import health_data.crud as health_data_crud
import health_targets.crud as health_targets_crud
import users.user_default_gear.crud as user_default_gear_crud
import users.user_integrations.crud as user_integrations_crud
import users.user_goals.crud as user_goals_crud
import users.user_privacy_settings.crud as users_privacy_settings_crud


class ExportPerformanceConfig(profile_utils.BasePerformanceConfig):
    """
    Configuration class for managing export performance parameters.
    This class provides configuration options to optimize data export operations by
    controlling batch sizes, memory limits, compression settings, and chunk sizes.
    It includes an adaptive configuration factory method that automatically adjusts
    settings based on available system memory.
    Attributes:
        batch_size (int): Number of records to process in a single batch. Default is 1000.
        max_memory_mb (int): Maximum memory usage in megabytes. Default is 1024.
        compression_level (int): Compression level (0-9, where 0 is no compression and
            9 is maximum compression). Default is 6.
        chunk_size (int): Size of data chunks in bytes for I/O operations. Default is 8192.
        enable_memory_monitoring (bool): Whether to enable memory usage monitoring during
            export operations. Default is True.
        timeout_seconds (int): Operation timeout in seconds. Default is 3600 (60 minutes).
    Example:
        >>> # Create with default settings
        >>> config = ExportPerformanceConfig()
        >>>
        >>> # Create with custom settings
        >>> config = ExportPerformanceConfig(batch_size=500, max_memory_mb=256)
        >>>
        >>> # Create with auto-detection based on system resources
        >>> config = ExportPerformanceConfig.get_auto_config()
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_memory_mb: int = 1024,
        compression_level: int = 6,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
        timeout_seconds: int = 3600,
    ):
        """
        Initialize the export service with configuration parameters.

        Args:
            batch_size (int, optional): Number of records to process in each batch. Defaults to 1000.
            max_memory_mb (int, optional): Maximum memory usage in megabytes before triggering cleanup. Defaults to 1024.
            compression_level (int, optional): Compression level for export files (0-9, where 9 is maximum compression). Defaults to 6.
            chunk_size (int, optional): Size of chunks in bytes for streaming operations. Defaults to 8192.
            enable_memory_monitoring (bool, optional): Whether to enable memory usage monitoring during export. Defaults to True.
            timeout_seconds (int, optional): Maximum time allowed for export operation in seconds. Defaults to 3600 (60 minutes).
        """
        super().__init__(batch_size, max_memory_mb, enable_memory_monitoring, timeout_seconds)
        self.compression_level = compression_level
        self.chunk_size = chunk_size

    @classmethod
    def _get_tier_configs(cls) -> Dict[str, Dict[str, Any]]:
        """
        Define tier-specific configuration settings for export operations.
        
        Returns:
            Dict[str, Dict[str, Any]]: Configuration dictionaries for memory tiers.
                Each dictionary contains parameters optimized for the corresponding memory tier.
        """
        return {
            "high": {
                "batch_size": 2000,
                "max_memory_mb": 2048,
                "compression_level": 6,
                "chunk_size": 16384,
                "timeout_seconds": 7200,
            },
            "medium": {
                "batch_size": 1000,
                "max_memory_mb": 1024,
                "compression_level": 4,
                "chunk_size": 8192,
                "timeout_seconds": 3600,
            },
            "low": {
                "batch_size": 500,
                "max_memory_mb": 512,
                "compression_level": 1,
                "chunk_size": 4096,
                "timeout_seconds": 1800,
            }
        }


class ExportService:
    """
    Service class for exporting user data including activities, gear, health information, and media files.
    This class handles the collection and export of comprehensive user data into a ZIP archive format.
    It provides methods for batched data collection to optimize memory usage, with configurable
    performance settings for handling large datasets efficiently.
    The export process includes:
    - User activities with associated components (laps, sets, streams, workout steps, media)
    - Gear and gear components
    - Health data and targets
    - User settings (default gear, integrations, goals, privacy settings)
    - Activity files and media files
    - User profile images
        user_id (int): The ID of the user whose data is being exported.
        db (Session): SQLAlchemy database session for data access.
        counts (Dict[str, int]): Dictionary tracking the count of each exported data type.
        performance_config (ExportPerformanceConfig): Configuration settings for performance
            optimization including batch size, memory limits, and compression level.
        >>> from sqlalchemy.orm import Session
        >>> db = Session()
        >>> export_service = ExportService(user_id=123, db=db)
        >>> user_data = {"id": 123, "name": "John Doe"}
        ...     # Process each chunk of the ZIP file
        - Uses batched processing to minimize memory usage during data collection
        - Implements memory monitoring with configurable thresholds
        - Provides graceful error handling with detailed logging
        - Supports timeout enforcement for long-running operations
        - All temporary files are automatically cleaned up after export
    """

    def __init__(
        self,
        user_id: int,
        db: Session,
        performance_config: ExportPerformanceConfig | None = None,
    ):
        """
        Initialize the ExportService with user ID, database session, and performance configuration.

        Args:
            user_id (int): The ID of the user for whom data will be exported.
            db (Session): The SQLAlchemy database session for querying data.
            performance_config (ExportPerformanceConfig | None): Configuration for performance tuning.
                If None, will use auto-detected configuration based on system resources.

        Attributes:
            user_id (int): Stores the user ID for the export operation.
            db (Session): Stores the database session for data access.
            counts (dict): Dictionary containing initialized count values for various entities.
            performance_config (ExportPerformanceConfig): Performance configuration settings.
        """
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

    def collect_user_activities_data(self) -> Dict[str, Any]:
        """
        Collects all activity-related data for a user using batched processing for memory efficiency.

        This method retrieves user activities and their associated components using pagination
        to limit memory usage. It processes activities in batches and handles errors gracefully
        for each component to ensure partial data collection is possible.

        Returns:
            Dict[str, Any]: A dictionary containing the following keys:
                - activities (list): List of user activity objects
                - laps (list): List of activity laps data
                - sets (list): List of activity sets data
                - streams (list): List of activity streams data
                - steps (list): List of activity workout steps data
                - media (list): List of activity media data
                - exercise_titles (list): List of exercise title objects
        Raises:
            DatabaseConnectionError: If a database error occurs during data collection
            DataCollectionError: If an unexpected error occurs during data collection
        Note:
            - Uses batched processing to minimize memory usage
            - Returns empty lists for each component if no activities are found
            - Filters out activities with None IDs before collecting related data
            - Logs warnings for missing data and errors for critical failures
            - Uses individual error handling for each component to allow partial collection
        """
        result = {
            "activities": [],
            "laps": [],
            "sets": [],
            "streams": [],
            "steps": [],
            "media": [],
            "exercise_titles": [],
        }

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
                return result

            result["activities"] = all_activities

            # Filter out activities with None IDs and collect valid IDs
            activity_ids = [
                activity.id for activity in all_activities if activity.id is not None
            ]

            if not activity_ids:
                core_logger.print_to_log(
                    f"No valid activity IDs found for user {self.user_id}", "warning"
                )
                return result

            # Collect related activity data with batched processing
            self._collect_activity_components_batched(
                result, activity_ids, all_activities
            )

            # Exercise titles don't depend on activity IDs
            try:
                exercise_titles = (
                    activity_exercise_titles_crud.get_activity_exercise_titles(self.db)
                )
                result["exercise_titles"] = exercise_titles or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect exercise titles: {err}", "warning", exc=err
                )
                result["exercise_titles"] = []

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting activities: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect activity data: {err}"
            ) from err
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error collecting activities: {err}", "error", exc=err
            )
            raise DataCollectionError(
                f"Failed to collect activity data: {err}"
            ) from err

        return result

    def _get_activities_batch(self, offset: int, limit: int) -> List[Any]:
        """
        Retrieve a batch of activities for the user with pagination support.
        This method fetches activities from the database using offset-based pagination,
        converting the offset to a page number for use with the underlying CRUD function.
        Activities are sorted by start_time in descending order (most recent first).
        Args:
            offset (int): The number of records to skip before starting to return results.
                         Used to calculate the page number for pagination.
            limit (int): The maximum number of activities to return in this batch.
        Returns:
            List[Any]: A list of activity objects for the specified page. Returns an empty
                      list if no activities are found or if an error occurs.
        Raises:
            Does not raise exceptions directly. Errors are logged and an empty list is returned.
        Example:
            >>> activities = self._get_activities_batch(offset=0, limit=50)
            >>> # Retrieves the first 50 activities
            >>> activities = self._get_activities_batch(offset=50, limit=50)
            >>> # Retrieves activities 51-100
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
            )

            return activities or []

        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get activities batch (offset={offset}, limit={limit}): {err}",
                "warning",
                exc=err,
            )
            return []

    def _collect_activity_components_batched(
        self,
        result: Dict[str, Any],
        activity_ids: List[int],
        user_activities: List[Any],
    ) -> None:
        """
        Collect activity components in batches to optimize memory usage.
        This method processes activity components (laps, sets, streams, steps, media) in smaller
        batches to reduce memory footprint during data collection. It iterates through activity IDs
        and retrieves associated components for each batch.
        Args:
            result (Dict[str, Any]): Dictionary to store collected component data, organized by
                component type (e.g., 'laps', 'sets', 'streams', 'steps', 'media').
            activity_ids (List[int]): List of activity IDs to process.
            user_activities (List[Any]): List of user activity objects corresponding to the activity IDs.
        Returns:
            None: Modifies the result dictionary in-place by adding component data.
        Note:
            - Uses half of the configured batch size for component processing to reduce memory usage
            - Monitors memory usage between batches
            - Logs progress information for each processed batch
        """
        # Process activity IDs in smaller batches to reduce memory usage
        batch_size = (
            self.performance_config.batch_size // 2
        )  # Smaller batches for components

        for i in range(0, len(activity_ids), batch_size):
            batch_ids = activity_ids[i : i + batch_size]
            batch_activities = user_activities[i : i + batch_size]

            profile_utils.check_memory_usage(
                f"component batch {i//batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

            # Collect each component type for this batch
            self._collect_activity_component_batch(
                result,
                "laps",
                activity_laps_crud.get_activities_laps,
                batch_ids,
                self.user_id,
                self.db,
                batch_activities,
            )

            self._collect_activity_component_batch(
                result,
                "sets",
                activity_sets_crud.get_activities_sets,
                batch_ids,
                self.user_id,
                self.db,
                batch_activities,
            )

            self._collect_activity_component_batch(
                result,
                "streams",
                activity_streams_crud.get_activities_streams,
                batch_ids,
                self.user_id,
                self.db,
                batch_activities,
            )

            self._collect_activity_component_batch(
                result,
                "steps",
                activity_workout_steps_crud.get_activities_workout_steps,
                batch_ids,
                self.user_id,
                self.db,
                batch_activities,
            )

            self._collect_activity_component_batch(
                result,
                "media",
                activity_media_crud.get_activities_media,
                batch_ids,
                self.user_id,
                self.db,
                batch_activities,
            )

            core_logger.print_to_log(
                f"Processed component batch {i//batch_size + 1} "
                f"({len(batch_ids)} activities)",
                "info",
            )

    def _collect_activity_component_batch(
        self, result: Dict, key: str, crud_func, *args
    ) -> None:
        """
        Collects and appends activity component data to a result dictionary.

        This method executes a CRUD function to retrieve activity component data and stores it
        in the result dictionary under the specified key. If data exists, it initializes the key
        as a list (if not present) and extends it with the retrieved data. Any exceptions during
        execution are logged as warnings.

        Args:
            result (Dict): The dictionary where collected data will be stored.
            key (str): The key under which the data will be stored in the result dictionary.
            crud_func: A callable function that retrieves the activity component data.
            *args: Variable length argument list to be passed to the crud_func.

        Returns:
            None: This method modifies the result dictionary in-place.

        Raises:
            No exceptions are raised; all exceptions are caught and logged as warnings.

        Example:
            >>> result = {}
            >>> self._collect_activity_component_batch(
            ...     result,
            ...     'streams',
            ...     get_activity_streams,
            ...     activity_id
            ... )
        """
        try:
            data = crud_func(*args)
            if data:
                if key not in result:
                    result[key] = []
                result[key].extend(data)
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to collect batch for {key}: {err}", "warning", exc=err
            )

    def _collect_activity_component(self, result: Dict, key: str, crud_func, *args):
        """
        Collect activity component data and store it in the result dictionary.

        This method attempts to retrieve data using the provided CRUD function and stores
        it in the result dictionary under the specified key. If the operation fails or
        returns None, an empty list is stored instead.

        Args:
            result (Dict): The dictionary where the collected data will be stored.
            key (str): The key under which the data will be stored in the result dictionary.
            crud_func: The CRUD function to be called for data collection.
            *args: Variable length argument list to be passed to the crud_func.

        Returns:
            None: The method modifies the result dictionary in place.

        Raises:
            No exceptions are raised. Exceptions from crud_func are caught and logged as warnings,
            with an empty list stored in the result dictionary for the given key.

        Side Effects:
            - Modifies the result dictionary by adding or updating the specified key.
            - Logs a warning message if data collection fails.
        """
        try:
            data = crud_func(*args)
            result[key] = data or []
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to collect {key}: {err}", "warning", exc=err
            )
            result[key] = []

    def collect_gear_data(self) -> Dict[str, Any]:
        """
        Collects all gear and gear component data for the user.
        This method retrieves both gear items and their associated components from the database
        for the specified user. It handles errors gracefully by logging warnings and returning
        empty lists for failed operations, while raising exceptions for critical database errors.
        Returns:
            Dict[str, Any]: A dictionary containing:
                - gears (list): List of gear items belonging to the user. Empty list if
                  collection fails or no gears exist.
                - gear_components (list): List of gear components belonging to the user.
                  Empty list if collection fails or no components exist.
        Raises:
            DatabaseConnectionError: If a SQLAlchemy database error occurs during data collection.
        Note:
            Individual collection failures (gears or components) are logged as warnings but don't
            prevent the method from returning partial results.
        """
        result = {"gears": [], "gear_components": []}

        try:
            # Collect gears
            try:
                gears = gear_crud.get_gear_user(self.user_id, self.db)
                result["gears"] = gears or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect gears: {err}", "warning", exc=err
                )
                result["gears"] = []

            # Collect gear components
            try:
                gear_components = gear_components_crud.get_gear_components_user(
                    self.user_id, self.db
                )
                result["gear_components"] = gear_components or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect gear components: {err}", "warning", exc=err
                )
                result["gear_components"] = []

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting gear data: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect gear data: {err}"
            ) from err

        return result

    def collect_health_data(self) -> Dict[str, Any]:
        """
        Collects health data and health targets for a specific user.
        This method retrieves all health data records and health targets associated with
        the user, handling errors gracefully by logging warnings and returning empty lists
        for failed operations.
        Returns:
            Dict[str, Any]: A dictionary containing:
                - health_data (list): List of health data records for the user, or empty list if retrieval fails
                - health_targets (list): List of health targets for the user, or empty list if retrieval fails
        Raises:
            DatabaseConnectionError: If a SQLAlchemy database error occurs during data collection
        Note:
            Individual collection failures (health_data or health_targets) are logged as warnings
            but do not raise exceptions. Only SQLAlchemy database errors will raise an exception.
        """
        result = {"health_data": [], "health_targets": []}

        try:
            # Collect health data
            try:
                health_data = health_data_crud.get_all_health_data_by_user_id(
                    self.user_id, self.db
                )
                result["health_data"] = health_data or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect health data: {err}", "warning", exc=err
                )
                result["health_data"] = []

            # Collect health targets
            try:
                health_targets = health_targets_crud.get_health_targets_by_user_id(
                    self.user_id, self.db
                )
                result["health_targets"] = health_targets or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect health targets: {err}", "warning", exc=err
                )
                result["health_targets"] = []

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting health data: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect health data: {err}"
            ) from err

        return result

    def collect_user_settings_data(self) -> Dict[str, Any]:
        """
        Collects all user settings data including default gear, goals, integrations, and privacy settings.
        This method retrieves various user settings from the database and compiles them into a
        dictionary. Each setting is collected individually with its own error handling to ensure
        partial data collection even if some queries fail.
        Returns:
            Dict[str, Any]: A dictionary containing:
                - user_default_gear: User's default gear settings or None if not found/error
                - user_integrations: User's integration settings or None if not found/error
                - user_goals: List of user goals or empty list if not found/error
                - user_privacy_settings: User's privacy settings or None if not found/error
        Raises:
            DatabaseConnectionError: If a database connection error occurs during data collection.
        Note:
            Individual collection failures are logged as warnings and result in None or empty
            values for the respective fields, allowing partial data collection to continue.
        """
        result = {
            "user_default_gear": None,
            "user_integrations": None,
            "user_goals": [],
            "user_privacy_settings": None,
        }

        try:
            # Collect user default gear
            try:
                user_default_gear = (
                    user_default_gear_crud.get_user_default_gear_by_user_id(
                        self.user_id, self.db
                    )
                )
                result["user_default_gear"] = user_default_gear
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user default gear: {err}", "warning", exc=err
                )
                result["user_default_gear"] = None

            # Collect user goals
            try:
                user_goals = user_goals_crud.get_user_goals_by_user_id(
                    self.user_id, self.db
                )
                result["user_goals"] = user_goals or []
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user goals: {err}", "warning", exc=err
                )
                result["user_goals"] = []

            # Collect user integrations
            try:
                user_integrations = (
                    user_integrations_crud.get_user_integrations_by_user_id(
                        self.user_id, self.db
                    )
                )
                result["user_integrations"] = user_integrations
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user integrations: {err}", "warning", exc=err
                )
                result["user_integrations"] = None

            # Collect user privacy settings
            try:
                user_privacy_settings = (
                    users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                        self.user_id, self.db
                    )
                )
                result["user_privacy_settings"] = user_privacy_settings
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to collect user privacy settings: {err}",
                    "warning",
                    exc=err,
                )
                result["user_privacy_settings"] = None

        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Database error collecting user settings: {err}", "error", exc=err
            )
            raise DatabaseConnectionError(
                f"Failed to collect user settings: {err}"
            ) from err

        return result

    def add_activity_files_to_zip(
        self, zipf: zipfile.ZipFile, user_activities: List[Any]
    ):
        """
        Add activity files to the zip archive for activities in the user's activity list.
        This method walks through the processed files directory and adds files matching
        activity IDs to the zip archive. Files are stored in an 'activity_files' subdirectory
        within the archive, maintaining the original directory structure.
        Args:
            zipf (zipfile.ZipFile): The zip file object to add files to.
            user_activities (List[Any]): List of activity objects containing IDs to match
                against file names.
        Raises:
            FileSystemError: If there's a critical error accessing the activity files directory.
        Notes:
            - Files are matched by comparing their filename (without extension) to activity IDs.
            - Missing or inaccessible files are logged as warnings and skipped.
            - The method increments self.counts["activity_files"] for each successfully added file.
            - Individual file errors do not stop processing of remaining files.
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
        self, zipf: zipfile.ZipFile, user_activities: List[Any]
    ):
        """
        Add activity media files to the ZIP archive for the specified user activities.
        This method walks through the activity media directory, identifies media files
        that belong to the user's activities, and adds them to the provided ZIP file
        under the 'activity_media' directory structure.
        Args:
            zipf (zipfile.ZipFile): The ZIP file object to write media files to.
            user_activities (List[Any]): List of activity objects containing user activities.
                Each activity must have an 'id' attribute used to match media files.
        Returns:
            None
        Raises:
            FileSystemError: If there's a file system error preventing access to the
                media files directory.
        Side Effects:
            - Increments self.counts["media"] for each successfully added media file
            - Logs warnings for missing files, read errors, or unexpected errors
            - Logs errors for file system access issues
        Notes:
            - Media files are matched to activities by parsing the filename prefix
              (before underscore) as the activity ID
            - Files that cannot be read or don't exist are skipped with a warning
            - Returns early if user_activities is empty or media directory doesn't exist
            - Media files are stored in the ZIP with relative paths under 'activity_media/'
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
        Add user profile images to the ZIP archive using optimized file operations.

        This method searches for user profile images in the configured user images directory,
        filters them by user ID, and adds matching images to the provided ZIP file using
        optimized directory traversal and file size monitoring.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object to add images to.

        Raises:
            FileSystemError: If there's a file system error accessing the user images directory.

        Note:
            - Images are stored in a 'user_images' subdirectory within the ZIP archive
            - Only images whose filename (without extension) matches the user_id are included
            - Uses os.scandir() for optimized directory traversal
            - Includes file size monitoring and warnings for large files
            - Individual file errors are logged as warnings and don't stop the process
            - Updates self.counts["user_images"] with the number of images added
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
        Recursively adds user image files from a directory to a ZIP archive.

        This method traverses the specified directory and its subdirectories, processing
        each image file found and adding it to the provided ZIP file object. It handles
        permission errors and OS errors gracefully by logging warnings without stopping
        the process.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object to which images will be added.
            images_dir (str): The path to the directory containing user images to process.

        Raises:
            PermissionError: Logged as a warning when access to a directory is denied.
            OSError: Logged as a warning when an OS-level error occurs during directory access.

        Note:
            This method follows symlinks for directory traversal but not for individual files.
            It delegates individual file processing to _process_user_image_file().
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
        Process and add a user image file to the export ZIP archive.
        This method handles the processing of user profile image files during the export operation.
        It performs validation, size checking, memory monitoring, and adds the file to the ZIP archive
        with appropriate error handling.
        Args:
            zipf (zipfile.ZipFile): The ZIP file object to write the image to.
            entry: A directory entry object (typically from os.scandir()) containing file information.
                   Must have 'name', 'path', and 'stat()' methods.
            images_dir (str): The base directory path where user images are stored. Used to calculate
                             relative paths within the ZIP archive.
        Returns:
            None
        Side Effects:
            - Writes the user image file to the ZIP archive under 'user_images/' directory
            - Increments self.counts["user_images"] counter on success
            - Logs warnings for large files (>10MB), permission errors, or other issues
            - May trigger memory usage checks for files larger than 5MB
        Raises:
            Does not raise exceptions - all errors are caught and logged as warnings:
            - FileNotFoundError: When the image file cannot be found
            - PermissionError: When access to the file is denied
            - OSError: For other OS-level file operation errors
            - Exception: For any unexpected errors during processing
        Notes:
            - Only processes files where the filename (without extension) matches self.user_id
            - Large files (>10MB) trigger warning logs
            - Files >5MB trigger memory usage monitoring via profile_utils.check_memory_usage()
            - All file paths in the ZIP are relative to maintain portability
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

    def write_data_to_zip(
        self, zipf: zipfile.ZipFile, data_collections: Dict[str, Any]
    ):
        """
        Write collected user data to a ZIP file in JSON format.
        This method organizes and writes various user data collections (activities, gear, health,
        settings, and user information) into separate JSON files within a ZIP archive. Each data
        collection is processed and converted from SQLAlchemy objects to dictionaries before being
        written.
        Args:
            zipf (zipfile.ZipFile): An open ZIP file object in write mode where the data will be stored.
            data_collections (Dict[str, Any]): A dictionary containing different categories of user data:
                - "activities" (dict): Contains activities, laps, sets, streams, steps, media, and exercise_titles
                - "gear" (dict): Contains gears and gear_components
                - "health" (dict): Contains health_data and health_targets
                - "settings" (dict): Contains user_default_gear, user_integrations, user_goals, and user_privacy_settings
                - "user" (Any): User profile information
        Returns:
            None
        Note:
            - Each data item is converted to a dictionary using profile_utils.sqlalchemy_obj_to_dict
            - Single objects are converted to single-item lists before processing
            - Empty data collections are skipped
            - All data files are written to a "data/" subdirectory within the ZIP
            - A counts.json file is written to track the number of records for each data type
        """
        # Prepare data for writing
        activities_data = data_collections.get("activities", {})
        gear_data = data_collections.get("gear", {})
        health_data = data_collections.get("health", {})
        settings_data = data_collections.get("settings", {})
        user_data = data_collections.get("user", {})

        # Define data to write with their target filenames
        data_to_write = [
            (activities_data.get("activities", []), "data/activities.json"),
            (activities_data.get("laps", []), "data/activity_laps.json"),
            (activities_data.get("sets", []), "data/activity_sets.json"),
            (activities_data.get("streams", []), "data/activity_streams.json"),
            (activities_data.get("steps", []), "data/activity_workout_steps.json"),
            (activities_data.get("media", []), "data/activity_media.json"),
            (
                activities_data.get("exercise_titles", []),
                "data/activity_exercise_titles.json",
            ),
            (gear_data.get("gears", []), "data/gears.json"),
            (gear_data.get("gear_components", []), "data/gear_components.json"),
            (health_data.get("health_data", []), "data/health_data.json"),
            (health_data.get("health_targets", []), "data/health_targets.json"),
            (settings_data.get("user_default_gear"), "data/user_default_gear.json"),
            (settings_data.get("user_integrations"), "data/user_integrations.json"),
            (settings_data.get("user_goals"), "data/user_goals.json"),
            (
                settings_data.get("user_privacy_settings"),
                "data/user_privacy_settings.json",
            ),
            (user_data, "data/user.json"),
            (self.counts, "counts.json"),
        ]

        for data, filename in data_to_write:
            if data:
                if not isinstance(data, (list, tuple)):
                    data = [data]
                dicts = [profile_utils.sqlalchemy_obj_to_dict(item) for item in data]
                profile_utils.write_json_to_zip(zipf, filename, dicts, self.counts)

    def generate_export_archive(
        self, user_dict: Dict[str, Any], timeout_seconds: int | None = 300
    ) -> Generator[bytes, None, None]:
        """
        Generate a ZIP archive containing all user data for export.

        This method creates a comprehensive archive of user data including activities,
        gear, health information, settings, and associated media files. The archive is
        generated as a stream to handle large datasets efficiently.

        Args:
            user_dict (Dict[str, Any]): Dictionary containing user profile information.
            timeout_seconds (int | None): Maximum time in seconds allowed for
                the export operation. If None, no timeout is enforced. Defaults to 300.

        Yields:
            bytes: Chunks of the ZIP archive file (8192 bytes each) for streaming.

        Raises:
            TimeoutError: If the operation exceeds the specified timeout_seconds.
            ZipCreationError: If there's an error creating the ZIP archive, including
                BadZipFile or LargeZipFile errors.
            MemoryAllocationError: If there's insufficient memory during archive creation
                or streaming.
            FileSystemError: If there's a file system error during the export process.

        Note:
            The method performs timeout checks at various stages of the export process
            to prevent long-running operations. All collected data is written to a
            temporary file that is automatically deleted after streaming is complete.

        Example:
            >>> for chunk in export_service.generate_export_archive(user_data):
            ...     # Process or send each chunk
            ...     pass
        """
        start_time = time.time()

        try:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                try:
                    # Use configurable compression level for performance tuning
                    # ZIP_DEFLATED ensures proper ZIP format with standard compression
                    # This creates a valid ZIP file that will be correctly detected by MIME type validators
                    compression_level = self.performance_config.compression_level
                    core_logger.print_to_log(
                        f"Creating ZIP with compression level {compression_level}",
                        "info",
                    )

                    # Note: Using 'w' mode creates a proper ZIP archive with correct headers
                    # The file will have the standard ZIP magic bytes (PK\x03\x04) at the start
                    with zipfile.ZipFile(
                        tmp,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                        compresslevel=compression_level,
                    ) as zipf:
                        core_logger.print_to_log(
                            f"Starting export for user {self.user_id}", "info"
                        )

                        # Collect all data with timeout checks
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log(
                            "Collecting activities data...", "info"
                        )
                        activities_data = self.collect_user_activities_data()

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Collecting gear data...", "info")
                        gear_data = self.collect_gear_data()

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Collecting health data...", "info")
                        health_data = self.collect_health_data()

                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Collecting settings data...", "info")
                        settings_data = self.collect_user_settings_data()

                        # Add files to ZIP with timeout checks
                        user_activities = activities_data["activities"]

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

                        # Organize data collections
                        data_collections = {
                            "activities": activities_data,
                            "gear": gear_data,
                            "health": health_data,
                            "settings": settings_data,
                            "user": user_dict,
                        }

                        # Write all data to ZIP
                        profile_utils.check_timeout(
                            timeout_seconds, start_time, ExportTimeoutError, "Export"
                        )
                        core_logger.print_to_log("Writing data to archive...", "info")
                        self.write_data_to_zip(zipf, data_collections)

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
