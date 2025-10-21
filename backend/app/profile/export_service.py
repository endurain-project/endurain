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


class ExportService:
    """
    Service class responsible for exporting user profile data as ZIP archives.

    This class handles the collection of user data from the database and file system,
    and packages it into a downloadable ZIP file format.
    """

    def __init__(self, user_id: int, db: Session):
        """
        Initialize the ExportService with user ID and database session.

        Args:
            user_id (int): The ID of the user for whom data will be exported.
            db (Session): The SQLAlchemy database session for querying data.

        Attributes:
            user_id (int): Stores the user ID for the export operation.
            db (Session): Stores the database session for data access.
            counts (dict): Dictionary containing initialized count values for various entities.
        """
        self.user_id = user_id
        self.db = db
        self.counts = self._initialize_counts()

    def _initialize_counts(self) -> Dict[str, int]:
        """
        Initialize and return a dictionary with count trackers for all exportable data types.

        Returns:
            Dict[str, int]: A dictionary mapping data type names to their initial count values.
                All counts start at 0 except for 'user' which starts at 1 to represent
                the single user being exported.
        """
        return {
            "media": 0,
            "activity_files": 0,
            "activities": 0,
            "activity_laps": 0,
            "activity_sets": 0,
            "activity_streams": 0,
            "activity_workout_steps": 0,
            "activity_media": 0,
            "activity_exercise_titles": 0,
            "gears": 0,
            "gear_components": 0,
            "health_data": 0,
            "health_targets": 0,
            "user_images": 0,
            "user": 1,
            "user_default_gear": 0,
            "user_integrations": 0,
            "user_goals": 0,
            "user_privacy_settings": 0,
        }

    def collect_user_activities_data(self) -> Dict[str, Any]:
        """
        Collects all activity-related data for a user.
        This method retrieves user activities and their associated components including laps,
        sets, streams, workout steps, media, and exercise titles. It handles errors gracefully
        for each component to ensure partial data collection is possible even if some components fail.
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
            # Try to get user activities
            user_activities = activities_crud.get_user_activities(self.user_id, self.db)

            if not user_activities:
                core_logger.print_to_log(
                    f"No activities found for user {self.user_id}", "info"
                )
                return result

            result["activities"] = user_activities

            # Filter out activities with None IDs and collect valid IDs
            activity_ids = [
                activity.id for activity in user_activities if activity.id is not None
            ]

            if not activity_ids:
                core_logger.print_to_log(
                    f"No valid activity IDs found for user {self.user_id}", "warning"
                )
                return result

            # Collect related activity data with individual error handling
            self._collect_activity_component(
                result,
                "laps",
                activity_laps_crud.get_activities_laps,
                activity_ids,
                self.user_id,
                self.db,
                user_activities,
            )

            self._collect_activity_component(
                result,
                "sets",
                activity_sets_crud.get_activities_sets,
                activity_ids,
                self.user_id,
                self.db,
                user_activities,
            )

            self._collect_activity_component(
                result,
                "streams",
                activity_streams_crud.get_activities_streams,
                activity_ids,
                self.user_id,
                self.db,
                user_activities,
            )

            self._collect_activity_component(
                result,
                "steps",
                activity_workout_steps_crud.get_activities_workout_steps,
                activity_ids,
                self.user_id,
                self.db,
                user_activities,
            )

            self._collect_activity_component(
                result,
                "media",
                activity_media_crud.get_activities_media,
                activity_ids,
                self.user_id,
                self.db,
                user_activities,
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
        Add user profile images to the ZIP archive.
        This method searches for user profile images in the configured user images directory,
        filters them by user ID, and adds matching images to the provided ZIP file.
        Args:
            zipf (zipfile.ZipFile): The ZIP file object to add images to.
        Raises:
            FileSystemError: If there's a file system error accessing the user images directory.
        Note:
            - Images are stored in a 'user_images' subdirectory within the ZIP archive
            - Only images whose filename (without extension) matches the user_id are included
            - Individual file errors are logged as warnings and don't stop the process
            - Updates self.counts["user_images"] with the number of images added
            - If the user images directory doesn't exist, logs a warning and returns early
        """
        try:
            if not os.path.exists(core_config.USER_IMAGES_DIR):
                core_logger.print_to_log(
                    f"User images directory does not exist: {core_config.USER_IMAGES_DIR}",
                    "warning",
                )
                return

            for root, _, files in os.walk(core_config.USER_IMAGES_DIR):
                for file in files:
                    try:
                        file_id, _ = os.path.splitext(file)
                        if str(self.user_id) == file_id:
                            file_path = os.path.join(root, file)

                            # Check if file exists and is readable
                            if not os.path.isfile(file_path):
                                core_logger.print_to_log(
                                    f"User image file not found: {file_path}", "warning"
                                )
                                continue

                            arcname = os.path.join(
                                "user_images",
                                os.path.relpath(file_path, core_config.USER_IMAGES_DIR),
                            )
                            zipf.write(file_path, arcname)
                            self.counts["user_images"] += 1

                    except (OSError, IOError) as err:
                        core_logger.print_to_log(
                            f"Failed to add user image {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue
                    except Exception as err:
                        core_logger.print_to_log(
                            f"Unexpected error adding user image {file}: {err}",
                            "warning",
                            exc=err,
                        )
                        continue

        except (OSError, IOError) as err:
            core_logger.print_to_log(
                f"File system error accessing user images: {err}", "error", exc=err
            )
            raise FileSystemError(
                f"Cannot access user images directory: {err}"
            ) from err

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
            timeout_seconds (int | None, optional): Maximum time in seconds allowed for
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
                    with zipfile.ZipFile(
                        tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
                    ) as zipf:
                        core_logger.print_to_log(
                            f"Starting export for user {self.user_id}", "info"
                        )

                        # Collect all data with timeout checks
                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log(
                            "Collecting activities data...", "info"
                        )
                        activities_data = self.collect_user_activities_data()

                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log("Collecting gear data...", "info")
                        gear_data = self.collect_gear_data()

                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log("Collecting health data...", "info")
                        health_data = self.collect_health_data()

                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log("Collecting settings data...", "info")
                        settings_data = self.collect_user_settings_data()

                        # Add files to ZIP with timeout checks
                        user_activities = activities_data["activities"]

                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log(
                            "Adding activity files to archive...", "info"
                        )
                        self.add_activity_files_to_zip(zipf, user_activities)

                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log(
                            "Adding activity media to archive...", "info"
                        )
                        self.add_activity_media_to_zip(zipf, user_activities)

                        self._check_timeout(timeout_seconds, start_time)
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
                        self._check_timeout(timeout_seconds, start_time)
                        core_logger.print_to_log("Writing data to archive...", "info")
                        self.write_data_to_zip(zipf, data_collections)

                        self._check_timeout(timeout_seconds, start_time)
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

                # Stream the file with error handling
                tmp.seek(0)
                chunk_count = 0
                while True:
                    try:
                        self._check_timeout(timeout_seconds, start_time)
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

    def _check_timeout(self, timeout_seconds, start_time):
        if timeout_seconds and (time.time() - start_time) > timeout_seconds:
            raise ExportTimeoutError(f"Export exceeded {timeout_seconds} seconds")
