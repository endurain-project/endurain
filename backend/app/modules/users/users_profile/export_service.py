"""Profile data export service for ZIP archive generation.

This module provides the ExportService class for exporting
user profile data including activities, health records, gear,
and settings to a downloadable ZIP archive with streaming. The
user's profile image is written by ``export_media_service``.

Key Features:
- Batched data collection for memory efficiency
- Streaming ZIP generation
- Automatic performance tier detection
- Memory and timeout monitoring
"""

import contextlib
import tempfile
import time
import zipfile
from collections.abc import Callable
from typing import IO, Any, BinaryIO, Self

import jasil.providers as platform_providers
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_goals.integration_service as users_goals_integration
import modules.users.users_integrations.constants as user_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.export_media_service as export_media_service
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
        super().__init__(
            batch_size=batch_size,
            max_memory_mb=max_memory_mb,
            timeout_seconds=timeout_seconds,
            chunk_size=chunk_size,
            enable_memory_monitoring=enable_memory_monitoring,
        )
        self.compression_level = compression_level

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
                compression_level=6,
                chunk_size=16384,
                timeout_seconds=7200,
            ),
            "medium": cls(
                batch_size=125,
                max_memory_mb=1024,
                compression_level=6,
                chunk_size=8192,
                timeout_seconds=3600,
            ),
            "low": cls(
                batch_size=50,
                max_memory_mb=512,
                compression_level=6,
                chunk_size=4096,
                timeout_seconds=1800,
            ),
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

    def collect_profile_sections(
        self,
        archive: users_profile_utils.ZipArchiveWriter,
        check_timeout: Callable[[], None],
    ) -> list[users_profile_contracts.ExportFiles]:
        """Run every registered profile section, in registration order.

        Args:
            archive: Where the sections write their entries.
            check_timeout: Raises when the export is out of time; run before each section.

        Returns:
            The work the sections left for after the read transaction is committed.

        Raises:
            DatabaseConnectionError: If a section fails on the database.
            DataCollectionError: If a section cannot collect its records.
            ExportTimeoutError: If the export runs out of time.
            MemoryAllocationError: If the memory limit is exceeded.
        """
        context = users_profile_contracts.ProfileExportContext(
            user_id=self.user_id,
            db=self.db,
            storage=self.storage,
            archive=archive,
            counts=self.counts,
            batch_size=self.performance_config.batch_size,
            check_memory=self._check_memory,
            check_timeout=check_timeout,
        )
        files: list[users_profile_contracts.ExportFiles] = []
        for section in users_contributor_registry.profile_sections():
            check_timeout()
            try:
                if isinstance(section, users_profile_contracts.ProfileRecordsSection):
                    archive.write_json(f"data/{section.key}.json", section.export(self.user_id, self.db))
                else:
                    after_commit = section.export(context)
                    if after_commit is not None:
                        files.append(after_commit)
            except (
                ExportTimeoutError,
                MemoryAllocationError,
                MemoryError,
                OSError,
                zipfile.BadZipFile,
                zipfile.LargeZipFile,
            ):
                raise
            except SQLAlchemyError as err:
                raise DatabaseConnectionError(f"Failed to collect {section.key}") from err
            except Exception as err:
                raise DataCollectionError(f"Failed to collect {section.key}: {err}") from err
        return files

    def _check_memory(self, operation: str) -> None:
        """Raise when the memory limit is exceeded.

        Args:
            operation: Description of the current operation.

        Raises:
            MemoryAllocationError: If the memory limit is exceeded.
        """
        users_profile_utils.check_memory_usage(
            operation, self.performance_config.max_memory_mb, self.performance_config.enable_memory_monitoring
        )

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
                    privacy_dict = [users_profile_utils.model_to_dict(user_privacy_settings)]
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

    def build_export_archive(self, user_dict: dict[str, Any], timeout_seconds: int | None = 300) -> BinaryIO:
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

                def check_export_timeout() -> None:
                    users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")

                # Database phase first: the registered sections and settings.
                writer = users_profile_utils.ZipArchiveWriter(zipf, self.counts)
                section_files = self.collect_profile_sections(writer, check_export_timeout)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                self.collect_user_settings_data(zipf)

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                users_profile_utils.write_json_to_zip(zipf, "data/user.json", [user_dict], self.counts)

                # Everything below reads object storage only, which can take a long time, so the
                # read transaction ends here instead of pinning a pool connection throughout.
                self.db.commit()

                for write_files in section_files:
                    check_export_timeout()
                    write_files()

                users_profile_utils.check_timeout(timeout_seconds, start_time, ExportTimeoutError, "Export")
                export_media_service.add_user_images_to_zip(
                    zipf, self.user_id, self.storage, self.counts, self.performance_config
                )

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
