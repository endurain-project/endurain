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
import time
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any, Self

import jasil.providers as platform_providers
from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_goals.integration_service as users_goals_integration
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_integrations.constants as users_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as users_integrations_schema
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    ImportAccountMismatchError,
    ImportArchiveFromOlderVersionError,
    ImportTimeoutError,
)

logger = core_logger.get_logger(__name__)


class ImportPerformanceConfig(profile_utils.BasePerformanceConfig):
    """Performance configuration for import operations.

    Attributes:
        batch_size: Number of items per batch.
        max_memory_mb: Maximum memory in megabytes.
        max_file_size_mb: Maximum archive size in megabytes; the upload limit, so no tier raises it.
        max_json_mb: Maximum size of one JSON data entry in megabytes; parsing it takes several
            times that in memory.
        max_activities: Maximum number of activities.
        max_entries: Maximum number of entries in the archive.
        max_uncompressed_mb: Maximum decompressed bytes read from the archive, in megabytes, whatever
            the archive declares.
        timeout_seconds: Operation timeout in seconds.
        chunk_size: Data chunk size in bytes.
        enable_memory_monitoring: Enable memory monitoring.
    """

    def __init__(
        self,
        batch_size: int = 125,
        max_memory_mb: int = 1024,
        max_file_size_mb: int = 500,
        max_json_mb: int = 128,
        max_activities: int = 10000,
        max_entries: int = 100000,
        max_uncompressed_mb: int = 2048,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        """Set the import limits; unset values come from the auto-detected tier."""
        super().__init__(
            batch_size=batch_size,
            max_memory_mb=max_memory_mb,
            timeout_seconds=timeout_seconds,
            chunk_size=chunk_size,
            enable_memory_monitoring=enable_memory_monitoring,
        )
        self.max_file_size_mb = max_file_size_mb
        self.max_json_mb = max_json_mb
        self.max_activities = max_activities
        self.max_entries = max_entries
        self.max_uncompressed_mb = max_uncompressed_mb

    @classmethod
    def _get_tier_configs(cls) -> dict[str, Self]:
        """Get the tier-specific configurations.

        Returns:
            Dictionary mapping tier names to their configs.
        """
        return {
            "high": cls(
                batch_size=250,
                max_memory_mb=2048,
                max_json_mb=256,
                max_activities=20000,
                timeout_seconds=7200,
                chunk_size=8192,
                enable_memory_monitoring=True,
            ),
            "medium": cls(
                batch_size=125,
                max_memory_mb=1024,
                max_json_mb=128,
                max_activities=10000,
                timeout_seconds=3600,
                chunk_size=8192,
                enable_memory_monitoring=True,
            ),
            "low": cls(
                batch_size=50,
                max_memory_mb=512,
                max_json_mb=64,
                max_activities=5000,
                timeout_seconds=1800,
                chunk_size=8192,
                enable_memory_monitoring=True,
            ),
        }


class ImportService:
    """Service for importing user profile data from ZIP archive.

    Attributes:
        user_id: ID of user to import data for.
        storage: The platform storage provider.
        db: Database session.
        counts: Dictionary tracking imported item counts.
        performance_config: Performance configuration.
    """

    def __init__(
        self,
        user_id: uuid.UUID,
        storage: platform_providers.StorageProvider,
        db: Session,
        performance_config: ImportPerformanceConfig | None = None,
        on_database_committed: Callable[[], None] | None = None,
    ):
        """Bind the import to a user, the platform storage and a database session.

        Args:
            user_id: The user the archive is imported into.
            storage: The platform storage provider.
            db: Database session.
            performance_config: Limits for this import; derived from the machine when omitted.
            on_database_committed: Called once the database rows are committed and the files
                are about to be written, so a caller can record that point.
        """
        self.user_id = user_id
        self.storage = storage
        self.db = db
        self.on_database_committed = on_database_committed
        self.counts = profile_utils.initialize_operation_counts(include_user_count=False)
        self._uncompressed_bytes = 0
        self.performance_config: ImportPerformanceConfig = (
            performance_config or ImportPerformanceConfig.get_auto_config()
        )

        logger.debug(
            "ImportService initialized",
            extra=core_logger.context(
                batch_size=self.performance_config.batch_size,
                max_memory_mb=self.performance_config.max_memory_mb,
                max_file_size_mb=self.performance_config.max_file_size_mb,
                timeout_seconds=self.performance_config.timeout_seconds,
            ),
        )

    def import_from_zip_data(self, zip_data: bytes) -> dict[str, int]:
        """Import profile data from ZIP file bytes.

        The database part is one transaction, committed once before the files are written, so a
        failure before that point leaves nothing imported and the archive can simply be imported
        again. A failure while writing files leaves the rows in place with some files missing.

        Args:
            zip_data: ZIP file content as bytes.

        Returns:
            The number of items imported, by kind.

        Raises:
            FileSizeError: If file exceeds size limit.
            FileFormatError: If ZIP format is invalid.
            FileSystemError: If file system error occurs.
            ImportAccountMismatchError: If the archive was exported from a different account.
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

        committed = False
        try:
            with zipfile.ZipFile(BytesIO(zip_data)) as zipf:
                if len(zipf.infolist()) > self.performance_config.max_entries:
                    raise FileSizeError(
                        f"ZIP file has {len(zipf.infolist())} entries, more than the "
                        f"{self.performance_config.max_entries} allowed"
                    )

                archive = profile_utils.ZipArchiveReader(
                    zipf,
                    max_json_bytes=self.performance_config.max_json_mb * 1024 * 1024,
                    max_uncompressed_bytes=self.performance_config.max_uncompressed_mb * 1024 * 1024,
                    max_memory_mb=self.performance_config.max_memory_mb,
                    enable_memory_monitoring=self.performance_config.enable_memory_monitoring,
                )
                self._require_same_account(archive.load_json("data/user.json"))

                def check_import_timeout() -> None:
                    profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")

                # Ids restored by a stage, keyed by the stage; a later stage reads the ones it depends on.
                ids: users_profile_contracts.ProfileIdMaps = {}

                # The user's own settings first: the profile height is read by the health records.
                check_import_timeout()
                user_data = archive.load_json("data/user.json")
                user_goals_data = archive.load_json("data/user_goals.json")
                user_integrations_data = archive.load_json("data/user_integrations.json")
                user_privacy_settings_data = archive.load_json("data/user_privacy_settings.json")

                self.collect_and_import_user_data(
                    user_data, user_goals_data, user_integrations_data, user_privacy_settings_data
                )
                del user_data, user_integrations_data
                del user_goals_data, user_privacy_settings_data

                # The registered sections, in order; a section reads only the ids of those before it.
                section_files = self.restore_profile_sections(archive, ids, check_import_timeout)

                # The default gear names gears, so it follows every section that restores them.
                check_import_timeout()
                self.import_user_default_gear(archive.load_json("data/user_default_gear.json"), ids)

                # Guard: if nothing was imported and there are no files to write, fail visibly
                # instead of returning a misleading "success" with zero counts.
                has_files = bool(section_files) or any(name.startswith("user_images/") for name in archive.names)
                if not has_files and all(v == 0 for v in self.counts.values()):
                    raise FileFormatError(
                        "Import completed with zero items imported. The ZIP file contains no importable data."
                    )

                # Everything above only staged rows, so the database part of the import is one unit:
                # it lands together here or, on any failure, not at all.
                self.db.commit()
                committed = True
                if self.on_database_committed is not None:
                    self.on_database_committed()
                logger.info(
                    "Profile import committed its database rows", extra=core_logger.context(user_id=self.user_id)
                )

                # Files, media and the photo come after the commit because they need the new
                # ids. They are keyed by those ids, so writing them again overwrites in place.
                check_import_timeout()
                for restore_files in section_files:
                    restore_files()
                self.add_user_images_from_zip(archive)

        except zipfile.BadZipFile as e:
            raise FileFormatError(f"Invalid ZIP file format: {e!s}") from e
        except OSError as e:
            raise FileSystemError(f"File system error during import: {e!s}") from e
        finally:
            if not committed:
                self.db.rollback()
                logger.warning(
                    "Profile import rolled back; nothing was imported", extra=core_logger.context(user_id=self.user_id)
                )

        return self.counts

    def _require_same_account(self, user_data: list[dict[str, Any]]) -> None:
        """Refuse an archive exported from another account.

        The archive's profile carries its owner's username and email, and the import writes that
        username onto the importing account. The archive belongs to this account when its username or
        its email is the account's, so an account renamed since the export still matches by email.

        Args:
            user_data: The archive's user records.

        Raises:
            ImportArchiveFromOlderVersionError: When the archive's account row carries an integer id.
            ImportAccountMismatchError: When the archive names a username or email and neither is the account's.
        """
        archived = user_data[0] if user_data else {}
        archived_id = archived.get("id")
        if isinstance(archived_id, int) and not isinstance(archived_id, bool):
            raise ImportArchiveFromOlderVersionError("This archive was exported by an older Endurain version")
        username, email = archived.get("username"), archived.get("email")
        if not username and not email:
            return
        account = users_integration.require_user(self.user_id, self.db)
        same_username = bool(username) and str(username).casefold() == account.username.casefold()
        same_email = bool(email) and str(email).casefold() == account.email.casefold()
        if not (same_username or same_email):
            raise ImportAccountMismatchError("The archive was exported from a different account")

    def collect_and_import_user_data(
        self,
        user_data: list[dict[str, Any]],
        user_goals_data: list[dict[str, Any]],
        user_integrations_data: list[dict[str, Any]],
        user_privacy_settings_data: list[dict[str, Any]],
    ) -> None:
        """Import user profile and related settings.

        Args:
            user_data: User profile data.
            user_goals_data: User goals data.
            user_integrations_data: Integration settings.
            user_privacy_settings_data: Privacy settings.
        """
        if user_data:
            # Import user profile
            user_profile = user_data[0]
            user_profile["id"] = self.user_id

            # Strict allow-list before persistence: profile import is a
            # self-service operation and MUST NOT be a back door for
            # privilege escalation. Even if the source ZIP was crafted
            # to set ``access_type``, ``active``, ``mfa_enabled``,
            # ``mfa_secret``, ``email_verified``, or
            # ``pending_admin_approval``, those fields are dropped here
            # before reaching the database.
            sanitized = {
                key: value for key, value in user_profile.items() if key in users_constants.PROFILE_SELF_SERVICE_FIELDS
            }
            profile_payload = users_schema.ProfileUpdate.model_validate(sanitized)
            users_integration.edit_profile(self.user_id, profile_payload, self.db, if_match="*")
            self.counts["user"] += 1
        else:
            logger.debug("No user data to import, but continuing with sub-settings")

        # Import user-related settings — always attempt, even if
        # user_data was empty, so that sub-setting data loaded from
        # the ZIP is not silently discarded.
        self.collect_and_import_user_goals(user_goals_data)
        self.collect_and_import_user_integrations(user_integrations_data)
        self.collect_and_import_user_privacy_settings(user_privacy_settings_data)

    def import_user_default_gear(
        self, user_default_gear_data: list[dict[str, Any]], ids: users_profile_contracts.ProfileIdMaps
    ) -> None:
        """Import user default gear settings with ID remapping.

        Args:
            user_default_gear_data: Default gear data.
            ids: The ids restored by the sections; the gear ids are read from them.
        """
        if not user_default_gear_data:
            logger.debug("No user default gear data to import")
            return
        if users_default_gear_integration.restore_profile_default_gear(
            user_default_gear_data[0], ids, self.user_id, self.db
        ):
            self.counts["user_default_gear"] += 1

    def restore_profile_sections(
        self,
        archive: profile_utils.ZipArchiveReader,
        ids: users_profile_contracts.ProfileIdMaps,
        check_timeout: Callable[[], None],
    ) -> list[users_profile_contracts.RestoreFiles]:
        """Restore every registered profile section, in registration order.

        Args:
            archive: Where the sections read their entries.
            ids: The ids restored so far; each section publishes its own under its key.
            check_timeout: Raises when the import is out of time; run before each section.

        Returns:
            The work the sections left for after the commit.
        """
        context = users_profile_contracts.ProfileImportContext(
            user_id=self.user_id,
            db=self.db,
            storage=self.storage,
            archive=archive,
            counts=self.counts,
            ids=ids,
            batch_size=self.performance_config.batch_size,
            check_memory=self._check_memory,
            check_timeout=check_timeout,
            check_activity_count=self._check_activity_count,
        )
        files: list[users_profile_contracts.RestoreFiles] = []
        for section in users_contributor_registry.profile_sections():
            check_timeout()
            if isinstance(section, users_profile_contracts.ProfileRecordsSection):
                records = archive.load_json(f"data/{section.key}.json")
                self.counts[section.key] = self.counts.get(section.key, 0) + section.restore(
                    records, self.user_id, ids, self.db
                )
                del records
            else:
                after_commit = section.restore(context)
                if after_commit is not None:
                    files.append(after_commit)
        return files

    def _check_memory(self, operation: str) -> None:
        """Raise when the memory limit is exceeded.

        Args:
            operation: Description of the current operation.

        Raises:
            MemoryAllocationError: If the memory limit is exceeded.
        """
        profile_utils.check_memory_usage(
            operation, self.performance_config.max_memory_mb, self.performance_config.enable_memory_monitoring
        )

    def _check_activity_count(self, count: int) -> None:
        """Raise when an archive lists more activities than an import allows.

        Args:
            count: The number of activities the archive lists.

        Raises:
            ActivityLimitError: If there are too many activities.
        """
        if count > self.performance_config.max_activities:
            raise ActivityLimitError(
                f"Too many activities ({count}). Maximum allowed: {self.performance_config.max_activities}"
            )

    def collect_and_import_user_integrations(self, user_integrations_data: list[dict[str, Any]]) -> None:
        """Import user integration settings.

        Args:
            user_integrations_data: Integration data.
        """
        if not user_integrations_data:
            logger.debug("No user integrations data to import")
            return

        # Strict allow-list: an archive may carry the sync preferences only. Tokens, client
        # credentials and OAuth state belong to the account that linked them; a crafted ZIP
        # must not be able to plant them on the importing account.
        integrations_data = {
            key: value
            for key, value in user_integrations_data[0].items()
            if key in users_integrations_constants.PORTABLE_INTEGRATION_FIELDS
        }
        if not integrations_data:
            logger.debug("No importable user integrations data")
            return

        try:
            user_integrations = users_integrations_schema.UserIntegrationsUpdate(**integrations_data)
        except ValidationError:
            logger.warning("Skipped invalid user integrations")
            return
        user_integrations_integration.edit_integrations(user_integrations, self.user_id, self.db)
        logger.debug("Imported user integrations")
        self.counts["user_integrations"] += 1

    def collect_and_import_user_goals(self, user_goals_data: list[dict[str, Any]]) -> None:
        """Import user goals data.

        Args:
            user_goals_data: List of user goal dictionaries.
        """
        if not user_goals_data:
            logger.debug("No user goals data to import")
            return

        imported_at = datetime.now(UTC)
        for index, goal_data in enumerate(user_goals_data):
            goal_data = users_profile_contracts.without_row_identity(goal_data)

            try:
                goal = user_goals_schema.UserGoalCreate(**goal_data)
            except ValidationError:
                logger.warning("Skipped an invalid user goal")
                continue
            try:
                with self.db.begin_nested():
                    users_goals_integration.create_goal(
                        self.user_id, goal, self.db, created_at=imported_at + timedelta(microseconds=index)
                    )
            except core_exceptions.ConflictError:
                logger.debug("Skipped a user goal the user already has")
                continue
            self.counts["user_goals"] += 1

        logger.debug("Imported user goals", extra=core_logger.context(count=self.counts["user_goals"]))

    def collect_and_import_user_privacy_settings(self, user_privacy_settings_data: list[dict[str, Any]]) -> None:
        """Import user privacy settings.

        Args:
            user_privacy_settings_data: Privacy settings data.
        """
        if not user_privacy_settings_data:
            logger.debug("No user privacy settings data to import")
            return

        privacy_data = user_privacy_settings_data[0]
        privacy_data = users_profile_contracts.without_row_identity(privacy_data)

        try:
            user_privacy_settings = users_privacy_settings_schema.UserPrivacySettingsUpdate(**privacy_data)
        except ValidationError:
            logger.warning("Skipped invalid user privacy settings")
            return
        users_privacy_settings_integration.edit_privacy_settings(
            self.user_id, user_privacy_settings, self.db, if_match="*"
        )
        logger.debug("Imported user privacy settings")
        self.counts["user_privacy_settings"] += 1

    def add_user_images_from_zip(
        self,
        archive: profile_utils.ZipArchiveReader,
    ) -> None:
        """Extract and import user images from ZIP.

        Args:
            archive: The archive to read from.
        """
        profile_utils.check_memory_usage(
            "user images import",
            self.performance_config.max_memory_mb,
            self.performance_config.enable_memory_monitoring,
        )

        for file_path in archive.names:
            path = file_path.replace("\\", "/")

            # Import user images
            if path.lower().endswith(tuple(file_uploads.IMAGE_CONTENT_TYPES)) and path.startswith("user_images/"):
                logger.debug("Processing a user image file", extra=core_logger.context(file_path=file_path))
                ext = os.path.splitext(path)[1].lower()
                new_file_name = f"{self.user_id}{ext}"

                # Read bytes from ZIP and save through the unified
                # validated-write pipeline so the entry is re-checked
                # as an image.
                image_limit = file_uploads.file_validator.config.limits.max_image_size
                file_bytes = archive.read_bytes(file_path, max_bytes=image_limit)
                try:
                    file_uploads.validate_bytes_sync(
                        file_bytes,
                        kind=file_uploads.UploadKind.IMAGE,
                        filename=new_file_name,
                    )
                except core_exceptions.DomainError as err:
                    logger.warning(
                        "Profile import dropped an invalid user image",
                        extra=core_logger.context(file_name=new_file_name, detail=err.detail),
                    )
                    continue
                users_integration.store_user_photo(self.user_id, ext, file_bytes, self.storage, self.db)
                self.counts["user_images"] += 1
