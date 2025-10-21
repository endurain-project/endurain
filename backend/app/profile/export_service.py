import os
import tempfile
import zipfile
from typing import Generator, Dict, Any, List
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
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
from profile.utils import sqlalchemy_obj_to_dict, write_json_to_zip


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
        Collects all activity-related data for a user from the database.
        This method retrieves a user's activities and all associated data including laps, sets,
        streams, workout steps, media, and exercise titles. If no activities are found or all
        activity IDs are None, it returns empty collections for all data types.
        Returns:
            Dict[str, Any]: A dictionary containing the following keys:
                - activities (list): List of user activity objects
                - laps (list): List of activity lap records
                - sets (list): List of activity set records
                - streams (list): List of activity stream data
                - steps (list): List of workout step records
                - media (list): List of activity media records
                - exercise_titles (list): List of exercise title definitions
        Note:
            Activities with None IDs are filtered out before collecting related data.
            If no valid activity IDs exist, all collections will be empty lists.
        """
        user_activities = activities_crud.get_user_activities(self.user_id, self.db)

        if not user_activities:
            return {
                "activities": [],
                "laps": [],
                "sets": [],
                "streams": [],
                "steps": [],
                "media": [],
                "exercise_titles": [],
            }

        # Filter out activities with None IDs and collect valid IDs
        activity_ids = [
            activity.id for activity in user_activities if activity.id is not None
        ]

        # If no valid activity IDs found, return empty collections
        if not activity_ids:
            return {
                "activities": [],
                "laps": [],
                "sets": [],
                "streams": [],
                "steps": [],
                "media": [],
                "exercise_titles": [],
            }

        # Collect related activity data
        laps = activity_laps_crud.get_activities_laps(
            activity_ids, self.user_id, self.db, user_activities
        )
        sets = activity_sets_crud.get_activities_sets(
            activity_ids, self.user_id, self.db, user_activities
        )
        streams = activity_streams_crud.get_activities_streams(
            activity_ids, self.user_id, self.db, user_activities
        )
        steps = activity_workout_steps_crud.get_activities_workout_steps(
            activity_ids, self.user_id, self.db, user_activities
        )
        media = activity_media_crud.get_activities_media(
            activity_ids, self.user_id, self.db, user_activities
        )
        exercise_titles = activity_exercise_titles_crud.get_activity_exercise_titles(
            self.db
        )

        return {
            "activities": user_activities,
            "laps": laps,
            "sets": sets,
            "streams": streams,
            "steps": steps,
            "media": media,
            "exercise_titles": exercise_titles,
        }

    def collect_gear_data(self) -> Dict[str, Any]:
        """
        Collect all gear-related data for a user.
        Retrieves both the user's gear items and their associated components from the database.
        Returns:
            Dict[str, Any]: A dictionary containing:
                - gears: List of gear items belonging to the user
                - gear_components: List of gear components belonging to the user
        Note:
            This method uses the user_id and db instance variables from the class.
        """
        gears = gear_crud.get_gear_user(self.user_id, self.db)
        gear_components = gear_components_crud.get_gear_components_user(
            self.user_id, self.db
        )

        return {"gears": gears, "gear_components": gear_components}

    def collect_health_data(self) -> Dict[str, Any]:
        """
        Collects all health-related data for the user.
        Retrieves both health data records and health targets associated with the user
        from the database using CRUD operations.
        Returns:
            Dict[str, Any]: A dictionary containing:
                - health_data: All health data records for the user
                - health_targets: Health targets set by the user
        Raises:
            May raise database-related exceptions from the underlying CRUD operations.
        """
        health_data = health_data_crud.get_all_health_data_by_user_id(
            self.user_id, self.db
        )
        health_targets = health_targets_crud.get_health_targets_by_user_id(
            self.user_id, self.db
        )

        return {"health_data": health_data, "health_targets": health_targets}

    def collect_user_settings_data(self) -> Dict[str, Any]:
        """
        Collect all user settings and preferences data.
        This method retrieves various user-specific settings including default gear,
        integrations, goals, and privacy settings from the database.
        Returns:
            Dict[str, Any]: A dictionary containing the following keys:
                - user_default_gear: Default gear settings for the user
                - user_goals: User's defined goals
                - user_integrations: User's integration configurations
                - user_privacy_settings: User's privacy preferences
        Raises:
            Database exceptions may be raised by the underlying CRUD operations.
        """
        user_default_gear = user_default_gear_crud.get_user_default_gear_by_user_id(
            self.user_id, self.db
        )
        user_goals = user_goals_crud.get_user_goals_by_user_id(self.user_id, self.db)
        user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
            self.user_id, self.db
        )
        user_privacy_settings = (
            users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                self.user_id, self.db
            )
        )

        return {
            "user_default_gear": user_default_gear,
            "user_integrations": user_integrations,
            "user_goals": user_goals,
            "user_privacy_settings": user_privacy_settings,
        }

    def add_activity_files_to_zip(
        self, zipf: zipfile.ZipFile, user_activities: List[Any]
    ):
        """
        Add activity files to the zip archive.
        This method walks through the processed files directory and adds files that match
        activity IDs from the provided list of user activities to the zip archive.
        Args:
            zipf (zipfile.ZipFile): The zip file object to write activity files to.
            user_activities (List[Any]): A list of activity objects, each containing an 'id'
                attribute used to match against file names.
        Returns:
            None: This method modifies the zip file in place and updates the internal
                'activity_files' counter.
        Notes:
            - Files are matched by comparing the filename (without extension) to activity IDs
            - Matched files are added to the 'activity_files' directory within the zip
            - The method increments self.counts["activity_files"] for each file added
            - If user_activities is empty or None, the method returns early without processing
        """
        if not user_activities:
            return

        for root, _, files in os.walk(core_config.FILES_PROCESSED_DIR):
            for file in files:
                file_id, _ = os.path.splitext(file)
                if any(str(activity.id) == file_id for activity in user_activities):
                    self.counts["activity_files"] += 1
                    file_path = os.path.join(root, file)
                    arcname = os.path.join(
                        "activity_files",
                        os.path.relpath(file_path, core_config.FILES_PROCESSED_DIR),
                    )
                    zipf.write(file_path, arcname)

    def add_activity_media_to_zip(
        self, zipf: zipfile.ZipFile, user_activities: List[Any]
    ):
        """
        Add activity media files to the ZIP archive for activities belonging to the user.
        This method walks through the activity media directory and adds files that belong to
        any of the user's activities to the ZIP archive. Files are matched by extracting the
        activity ID from the filename (format: {activity_id}_{...}.{ext}) and comparing it
        against the provided list of user activities.
        Args:
            zipf (zipfile.ZipFile): The ZIP file object to write media files to.
            user_activities (List[Any]): List of activity objects that have an 'id' attribute.
                Only media files matching these activity IDs will be added to the archive.
        Returns:
            None
        Side Effects:
            - Increments self.counts["media"] for each media file added
            - Writes matching media files to the ZIP archive under the "activity_media" directory
            - Returns early if user_activities is empty or None
        Note:
            The method assumes media filenames follow the pattern: {activity_id}_{description}.{ext}
            where activity_id is extracted by splitting on the first underscore.
        """
        if not user_activities:
            return

        for root, _, files in os.walk(core_config.ACTIVITY_MEDIA_DIR):
            for file in files:
                file_id, _ = os.path.splitext(file)
                file_activity_id = file_id.split("_")[0]
                if any(
                    str(activity.id) == file_activity_id for activity in user_activities
                ):
                    self.counts["media"] += 1
                    file_path = os.path.join(root, file)
                    arcname = os.path.join(
                        "activity_media",
                        os.path.relpath(file_path, core_config.ACTIVITY_MEDIA_DIR),
                    )
                    zipf.write(file_path, arcname)

    def add_user_images_to_zip(self, zipf: zipfile.ZipFile):
        """
        Adds user-specific images to the provided ZIP file.

        This method walks through the user images directory and adds files whose names
        (without extension) match the current user's ID to the ZIP archive.

        Args:
            zipf (zipfile.ZipFile): The ZIP file object to write the user images to.

        Side Effects:
            - Increments self.counts["user_images"] for each matching image found.
            - Writes matching image files to the ZIP archive under the "user_images" directory.

        Notes:
            - Files are identified by comparing the file name (without extension) to the user_id.
            - The archive structure preserves the relative path from USER_IMAGES_DIR.
        """
        for root, _, files in os.walk(core_config.USER_IMAGES_DIR):
            for file in files:
                file_id, _ = os.path.splitext(file)
                if str(self.user_id) == file_id:
                    self.counts["user_images"] += 1
                    file_path = os.path.join(root, file)
                    arcname = os.path.join(
                        "user_images",
                        os.path.relpath(file_path, core_config.USER_IMAGES_DIR),
                    )
                    zipf.write(file_path, arcname)

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
            - Each data item is converted to a dictionary using sqlalchemy_obj_to_dict
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
                dicts = [sqlalchemy_obj_to_dict(item) for item in data]
                write_json_to_zip(zipf, filename, dicts, self.counts)

    def generate_export_archive(
        self, user_dict: Dict[str, Any]
    ) -> Generator[bytes, None, None]:
        """
        Generate a ZIP archive containing all user data for export.
        This method creates a temporary ZIP file containing the user's activities, gear,
        health data, settings, and associated media files. The archive is streamed in
        chunks to support efficient memory usage for large exports.
        Args:
            user_dict (Dict[str, Any]): Dictionary containing user profile information
                to be included in the export.
        Yields:
            bytes: Chunks of the ZIP archive file (8192 bytes each) for streaming
                download.
        Note:
            The temporary file is automatically deleted after streaming is complete.
            The ZIP file uses DEFLATE compression with compression level 6 to balance
            file size and processing time.
        """
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            with zipfile.ZipFile(
                tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as zipf:
                # Collect all data
                activities_data = self.collect_user_activities_data()
                gear_data = self.collect_gear_data()
                health_data = self.collect_health_data()
                settings_data = self.collect_user_settings_data()

                # Add files to ZIP
                user_activities = activities_data["activities"]
                self.add_activity_files_to_zip(zipf, user_activities)
                self.add_activity_media_to_zip(zipf, user_activities)
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
                self.write_data_to_zip(zipf, data_collections)

            # Stream the file
            tmp.seek(0)
            while True:
                chunk = tmp.read(8192)
                if not chunk:
                    break
                yield chunk
