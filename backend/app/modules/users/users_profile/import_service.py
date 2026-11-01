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
from collections.abc import Callable
from io import BytesIO
from typing import Any

import jasil.providers as platform_providers
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.activities.contributor_registry as activities_contributor_registry
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.gears.gear_components.schema as gear_components_schema
import modules.health.health_fasting.integration_service as health_fasting_integration
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_poop.integration_service as health_poop_integration
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.integration_service as health_steps_integration
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_water.integration_service as health_water_integration
import modules.health.health_water.schema as health_water_schema
import modules.health.health_weight.integration_service as health_weight_integration
import modules.health.health_weight.schema as health_weight_schema
import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_default_gear.schema as user_default_gear_schema
import modules.users.users_goals.integration_service as users_goals_integration
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_integrations.constants as users_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as users_integrations_schema
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    FileSizeError,
    FileSystemError,
    ImportTimeoutError,
    JSONParseError,
)

logger = core_logger.get_logger(__name__)

#: What an archive carries of a row's identity: the exporting account's id, owner and version, none of which an import writes.
_ROW_IDENTITY = frozenset({"id", "user_id", "version"})

#: The health record kinds imported beside weight, each with its schema and the call that stages one
#: for a user. The call returns whether it stored the record, so a record the user already has is not counted.
_HEALTH_RECORD_IMPORTS: dict[str, tuple[type[BaseModel], Callable[[int, Any, Session], Any]]] = {
    "health_sleep": (health_sleep_schema.HealthSleepCreate, health_sleep_integration.upsert_health_sleep),
    "health_steps": (health_steps_schema.HealthStepsCreate, health_steps_integration.upsert_health_steps),
    "health_water": (health_water_schema.HealthWaterCreate, health_water_integration.upsert_health_water),
    "health_fasting": (health_fasting_schema.HealthFastingCreate, health_fasting_integration.import_health_fasting),
    "health_poop": (health_poop_schema.HealthPoopCreate, health_poop_integration.import_health_poop),
}

#: Archive folders holding the files written after the database rows are committed.
_FILE_FOLDERS = ("activity_files/", "activity_media/", "user_images/")


def _without_row_identity(data: dict[str, Any]) -> dict[str, Any]:
    """Drop the row identity an archive carries, leaving the fields an import writes.

    Args:
        data: One exported row.

    Returns:
        The row without its id, owner and version.
    """
    return {key: value for key, value in data.items() if key not in _ROW_IDENTITY}


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
    def _get_tier_configs(cls) -> dict[str, dict[str, Any]]:
        """Get tier-specific configuration dictionaries.

        Returns:
            Dictionary mapping tier names to config dicts.
        """
        return {
            "high": {
                "batch_size": 250,
                "max_memory_mb": 2048,
                "max_json_mb": 256,
                "max_activities": 20000,
                "timeout_seconds": 7200,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "medium": {
                "batch_size": 125,
                "max_memory_mb": 1024,
                "max_json_mb": 128,
                "max_activities": 10000,
                "timeout_seconds": 3600,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
            "low": {
                "batch_size": 50,
                "max_memory_mb": 512,
                "max_json_mb": 64,
                "max_activities": 5000,
                "timeout_seconds": 1800,
                "chunk_size": 8192,
                "enable_memory_monitoring": True,
            },
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
        user_id: int,
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

    async def import_from_zip_data(self, zip_data: bytes) -> dict[str, Any]:
        """Import profile data from ZIP file bytes.

        The database part is one transaction, committed once before the files are written, so a
        failure before that point leaves nothing imported and the archive can simply be imported
        again. A failure while writing files leaves the rows in place with some files missing.

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

        committed = False
        try:
            with zipfile.ZipFile(BytesIO(zip_data)) as zipf:
                file_list = set(zipf.namelist())
                if len(zipf.infolist()) > self.performance_config.max_entries:
                    raise FileSizeError(
                        f"ZIP file has {len(zipf.infolist())} entries, more than the "
                        f"{self.performance_config.max_entries} allowed"
                    )

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

                self._restore_global_activity_components(zipf)

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

                health_records = {
                    name: self._load_single_json(zipf, f"data/{name}.json") for name in _HEALTH_RECORD_IMPORTS
                }
                await self.collect_and_import_health_records(health_records)
                del health_records

                # Guard: if nothing was imported and there are no files to write, fail visibly
                # instead of returning a misleading "success" with zero counts.
                has_files = any(name.startswith(_FILE_FOLDERS) for name in file_list)
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
                profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")
                await self.add_activity_files_from_zip(zipf, file_list, activities_id_mapping)
                await self.add_activity_media_from_zip(zipf, file_list, activities_id_mapping)
                await self.add_user_images_from_zip(zipf, file_list)

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

        return {"detail": "Import completed", "imported": self.counts}

    def _load_single_json(self, zipf: zipfile.ZipFile, filename: str, check_memory: bool = True) -> list[Any]:
        """Load and parse JSON file from ZIP archive.

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
                logger.warning(
                    "Expected data file not found in ZIP archive", extra=core_logger.context(filename=filename)
                )
                return []

            data = json.loads(self._read_zip_entry(zipf, filename))

            if not isinstance(data, list):
                logger.warning(
                    "Expected a list in a data file, returning an empty list",
                    extra=core_logger.context(filename=filename, found_type=type(data).__name__),
                )
                return []

            logger.debug("Loaded items from a data file", extra=core_logger.context(count=len(data), filename=filename))

            if check_memory:
                profile_utils.check_memory_usage(
                    f"loading {filename}",
                    self.performance_config.max_memory_mb,
                    self.performance_config.enable_memory_monitoring,
                )

            return data
        except json.JSONDecodeError as err:
            raise JSONParseError(f"Failed to parse JSON from {filename}: {err}") from err

    def _restore_global_activity_components(self, zipf: zipfile.ZipFile) -> None:
        """Load and restore every global activity contribution once."""
        for contributor in activities_contributor_registry.profile_global_contributors():
            records = self._load_single_json(zipf, contributor.archive_path, check_memory=False)
            restored = contributor.restore(records, self.db)
            self.counts[contributor.count_key] += restored
        logger.debug("Restored the global activity components", extra=core_logger.context(user_id=self.user_id))

    def _read_zip_entry(
        self,
        zipf: zipfile.ZipFile,
        filename: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        """Read a ZIP entry after checking its declared size.

        Args:
            zipf: ZipFile instance to read from.
            filename: Name of the entry to read.
            max_bytes: Optional byte cap for this entry. Defaults
                to the import performance JSON cap.

        Returns:
            Entry bytes.

        Raises:
            FileSizeError: If the entry exceeds the allowed size.
        """
        limit = max_bytes if max_bytes is not None else self.performance_config.max_json_mb * 1024 * 1024
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
                self._uncompressed_bytes += len(chunk)
                if self._uncompressed_bytes > self.performance_config.max_uncompressed_mb * 1024 * 1024:
                    raise FileSizeError(
                        f"The archive's uncompressed size exceeds {self.performance_config.max_uncompressed_mb}MB"
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    async def collect_and_import_gears_data(self, gears_data: list[Any]) -> dict[int, int]:
        """Import gear data and create ID mappings.

        Args:
            gears_data: List of gear data dictionaries.

        Returns:
            Dictionary mapping old gear IDs to new IDs.
        """
        gears_id_mapping: dict[int, int] = {}

        if not gears_data:
            logger.debug("No gears data to import")
            return gears_id_mapping

        for gear_data in gears_data:
            gear_data["user_id"] = self.user_id
            original_id = gear_data.get("id")
            gear_data.pop("id", None)
            gear_data.pop("version", None)

            try:
                gear = gear_schema.GearCreate(**gear_data)
            except ValidationError:
                logger.warning("Skipped an invalid gear")
                continue
            gears_id_mapping[original_id] = self._import_gear(gear)
            self.counts["gears"] += 1

        logger.debug("Imported gears", extra=core_logger.context(count=self.counts["gears"]))
        return gears_id_mapping

    def _import_gear(self, gear: gear_schema.GearCreate) -> int:
        """Import one gear, tolerating what the user already has.

        A gear whose nickname the user already has maps onto that gear. A provider gear
        ID the user already holds on another gear is dropped, so the archive cannot make
        the import fail.

        Args:
            gear: The gear from the archive.

        Returns:
            The ID of the gear the archived one maps to.
        """
        existing = gear_integration.get_gear_user_by_nickname(self.user_id, gear.nickname, self.db)
        if existing is not None:
            return existing.id
        try:
            with self.db.begin_nested():
                return gear_integration.create_gear(gear, self.user_id, self.db).id
        except core_exceptions.ConflictError:
            existing = gear_integration.get_gear_user_by_nickname(self.user_id, gear.nickname, self.db)
            if existing is not None:
                return existing.id
            logger.warning("Dropped the provider gear IDs of an imported gear that are already taken")
        without_ids = gear.model_copy(update={"strava_gear_id": None, "garminconnect_gear_id": None})
        with self.db.begin_nested():
            return gear_integration.create_gear(without_ids, self.user_id, self.db).id

    async def collect_and_import_gear_components_data(
        self, gear_components_data: list[Any], gears_id_mapping: dict[int, int]
    ) -> None:
        """Import gear components data with ID remapping.

        Args:
            gear_components_data: List of component dicts.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if not gear_components_data:
            logger.debug("No gear components data to import")
            return

        for gear_component_data in gear_components_data:
            new_gear_id = gears_id_mapping.get(gear_component_data.get("gear_id"))
            if new_gear_id is None:
                logger.warning("Skipped a gear component whose gear is not in the archive")
                continue
            gear_component_data["gear_id"] = new_gear_id

            for owner_or_derived in ("id", "version", "user_id", "current_distance", "current_time"):
                gear_component_data.pop(owner_or_derived, None)

            try:
                gear_component = gear_components_schema.GearComponentCreate(**gear_component_data)
            except ValidationError:
                logger.warning("Skipped an invalid gear component")
                continue
            if not gear_components_schema.is_retired_after_purchase(
                gear_component.purchase_date, gear_component.retired_date
            ):
                logger.warning("Skipped a gear component retired on or before its purchase date")
                continue
            gear_components_integration.create_gear_component(gear_component, self.user_id, self.db)
            self.counts["gear_components"] += 1

        logger.debug("Imported gear components", extra=core_logger.context(count=self.counts["gear_components"]))

    async def collect_and_import_user_data(
        self,
        user_data: list[Any],
        user_default_gear_data: list[Any],
        user_goals_data: list[Any],
        user_integrations_data: list[Any],
        user_privacy_settings_data: list[Any],
        gears_id_mapping: dict[int, int],
    ) -> None:
        """Import user profile and related settings.

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
        await self.collect_and_import_user_default_gear(user_default_gear_data, gears_id_mapping)
        await self.collect_and_import_user_goals(user_goals_data)
        await self.collect_and_import_user_integrations(user_integrations_data)
        await self.collect_and_import_user_privacy_settings(user_privacy_settings_data)

    async def collect_and_import_user_default_gear(
        self, user_default_gear_data: list[Any], gears_id_mapping: dict[int, int]
    ) -> None:
        """Import user default gear settings with ID remapping.

        Args:
            user_default_gear_data: Default gear data.
            gears_id_mapping: Mapping of old to new gear IDs.
        """
        if not user_default_gear_data:
            logger.debug("No user default gear data to import")
            return

        if users_default_gear_integration.get_default_gear(self.user_id, self.db) is None:
            logger.debug("No existing user default gear, creating new record")
            users_default_gear_integration.create_default_gear(self.user_id, self.db)

        gear_data = user_default_gear_data[0]
        # The archive's record and owner are the exporting account's; the update names neither.
        gear_data = _without_row_identity(gear_data)

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

        try:
            user_default_gear = user_default_gear_schema.UsersDefaultGearUpdate(**gear_data)
        except ValidationError:
            logger.warning("Skipped invalid user default gear")
            return
        users_default_gear_integration.edit_default_gear(user_default_gear, self.user_id, self.db, if_match="*")
        logger.debug("Imported user default gear")
        self.counts["user_default_gear"] += 1

    async def collect_and_import_user_integrations(self, user_integrations_data: list[Any]) -> None:
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
            user_integrations = users_integrations_schema.UsersIntegrationsUpdate(**integrations_data)
        except ValidationError:
            logger.warning("Skipped invalid user integrations")
            return
        user_integrations_integration.edit_integrations(user_integrations, self.user_id, self.db)
        logger.debug("Imported user integrations")
        self.counts["user_integrations"] += 1

    async def collect_and_import_user_goals(self, user_goals_data: list[Any]) -> None:
        """Import user goals data.

        Args:
            user_goals_data: List of user goal dictionaries.
        """
        if not user_goals_data:
            logger.debug("No user goals data to import")
            return

        for goal_data in user_goals_data:
            goal_data = _without_row_identity(goal_data)

            try:
                goal = user_goals_schema.UsersGoalCreate(**goal_data)
            except ValidationError:
                logger.warning("Skipped an invalid user goal")
                continue
            try:
                with self.db.begin_nested():
                    users_goals_integration.create_goal(self.user_id, goal, self.db)
            except core_exceptions.ConflictError:
                logger.debug("Skipped a user goal the user already has")
                continue
            self.counts["user_goals"] += 1

        logger.debug("Imported user goals", extra=core_logger.context(count=self.counts["user_goals"]))

    async def collect_and_import_user_privacy_settings(self, user_privacy_settings_data: list[Any]) -> None:
        """Import user privacy settings.

        Args:
            user_privacy_settings_data: Privacy settings data.
        """
        if not user_privacy_settings_data:
            logger.debug("No user privacy settings data to import")
            return

        privacy_data = user_privacy_settings_data[0]
        privacy_data = _without_row_identity(privacy_data)

        try:
            user_privacy_settings = users_privacy_settings_schema.UsersPrivacySettingsUpdate(**privacy_data)
        except ValidationError:
            logger.warning("Skipped invalid user privacy settings")
            return
        users_privacy_settings_integration.edit_privacy_settings(
            self.user_id, user_privacy_settings, self.db, if_match="*"
        )
        logger.debug("Imported user privacy settings")
        self.counts["user_privacy_settings"] += 1

    async def collect_and_import_activity_components(
        self,
        component_data: dict[str, list[dict[str, Any]]],
        original_activity_id: int,
        new_activity: activity_schema.ActivityRead,
    ) -> None:
        """Import contributed components for a single restored activity.

        Args:
            component_data: Records keyed by profile contributor key.
            original_activity_id: Old activity ID.
            new_activity: New activity object.
        """
        for contributor in activities_contributor_registry.profile_activity_contributors():
            restored = contributor.restore(
                component_data.get(contributor.key, []),
                original_activity_id,
                new_activity,
                self.db,
            )
            self.counts[contributor.count_key] += restored

    async def collect_and_import_activities_data_batched(
        self,
        zipf: zipfile.ZipFile,
        file_list: set[str],
        gears_id_mapping: dict[int, int],
        start_time: float,
        timeout_seconds: int,
    ) -> dict[int, int]:
        """Import activities in batches to manage memory.

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
            logger.debug("No activities data to import")
            return activities_id_mapping

        # Check activity count limit
        if len(activities_data) > self.performance_config.max_activities:
            raise ActivityLimitError(
                f"Too many activities ({len(activities_data)}). "
                f"Maximum allowed: {self.performance_config.max_activities}"
            )

        contributors = activities_contributor_registry.profile_activity_contributors()
        component_files: dict[str, list[str]] = {}
        component_records: dict[str, list[Any]] = {}
        for contributor in contributors:
            if contributor.split:
                component_files[contributor.key] = self._get_split_files_list(
                    file_list,
                    contributor.archive_path.removesuffix(".json"),
                )
            else:
                component_records[contributor.key] = self._load_single_json(
                    zipf,
                    contributor.archive_path,
                    check_memory=False,
                )

        logger.debug(
            "Importing activities with batched component loading", extra=core_logger.context(count=len(activities_data))
        )

        # Process activities in batches
        batch_size = self.performance_config.batch_size
        for batch_start in range(0, len(activities_data), batch_size):
            profile_utils.check_timeout(timeout_seconds, start_time, ImportTimeoutError, "Import")

            batch_end = min(batch_start + batch_size, len(activities_data))
            activities_batch = activities_data[batch_start:batch_end]

            logger.debug(
                "Processing an activities batch",
                extra=core_logger.context(
                    batch_number=batch_start // batch_size + 1, batch_start=batch_start, batch_end=batch_end
                ),
            )

            batch_components: dict[str, list[dict[str, Any]]] = {}
            for contributor in contributors:
                if contributor.split:
                    batch_components[contributor.key] = self._load_components_for_batch(
                        zipf,
                        component_files[contributor.key],
                        activities_batch,
                        contributor.key,
                    )
                else:
                    batch_components[contributor.key] = self._filter_components_for_batch(
                        component_records.get(contributor.key, []),
                        activities_batch,
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

                activity = activity_contracts.ActivityCore(**activity_data)
                # Bulk restore deliberately does not publish activity.created;
                # see integration_service.restore_activity for why.
                new_activity = activity_integration.restore_activity(activity, self.db)

                if original_activity_id is not None and new_activity.id is not None:
                    activities_id_mapping[original_activity_id] = new_activity.id

                    # Import activity components using batch-loaded data
                    await self.collect_and_import_activity_components(
                        batch_components,
                        original_activity_id,
                        new_activity,
                    )

                self.counts["activities"] += 1

            # Clear batch data from memory
            del batch_components
            profile_utils.check_memory_usage(
                f"activities batch {batch_start // batch_size + 1}",
                self.performance_config.max_memory_mb,
                self.performance_config.enable_memory_monitoring,
            )

        logger.debug("Imported activities", extra=core_logger.context(count=self.counts["activities"]))
        return activities_id_mapping

    @staticmethod
    def _filter_components_for_batch(
        records: list[Any],
        activities_batch: list[Any],
    ) -> list[dict[str, Any]]:
        """Filter in-memory component records to the current activity batch."""
        activity_ids = {
            activity.get("id")
            for activity in activities_batch
            if isinstance(activity, dict) and activity.get("id") is not None
        }
        return [record for record in records if isinstance(record, dict) and record.get("activity_id") in activity_ids]

    def _get_split_files_list(self, file_list: set[str], base_filename: str) -> list[str]:
        """Get list of split component files from ZIP.

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
        """Load components only for activities in current batch.

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
                if not isinstance(components, list):
                    logger.warning(
                        "Expected a list in a component file",
                        extra=core_logger.context(filename=filename, found_type=type(components).__name__),
                    )
                    continue
                # Only keep components for activities in this batch
                filtered = [
                    component
                    for component in components
                    if isinstance(component, dict) and component.get("activity_id") in batch_activity_ids
                ]
                all_components.extend(filtered)

                if filtered:
                    logger.debug(
                        "Loaded components for the batch",
                        extra=core_logger.context(
                            count=len(filtered),
                            total_count=len(components),
                            component_name=component_name,
                            filename=filename,
                        ),
                    )
            except json.JSONDecodeError as err:
                logger.warning(
                    "Failed to parse a component file", extra=core_logger.context(filename=filename, error=err)
                )
            except (FileFormatError, FileSizeError, OSError) as err:
                logger.warning(
                    "Error loading a component file", extra=core_logger.context(filename=filename, error=err)
                )

        return all_components

    async def collect_and_import_health_weight(
        self, health_weight_data: list[Any], health_targets_data: list[Any]
    ) -> None:
        """Import health data and targets.

        Args:
            health_weight_data: List of health data records.
            health_targets_data: List of health target records.
        """
        # Import health data
        if health_weight_data:
            for health_weight in health_weight_data:
                health_weight = _without_row_identity(health_weight)

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

                try:
                    data = health_weight_schema.HealthWeightCreate(**health_weight)
                except ValidationError:
                    logger.warning("Skipped an invalid health weight record")
                    continue
                health_weight_integration.upsert_health_weight(self.user_id, data, self.db)
                self.counts["health_weight"] += 1
            logger.debug(
                "Imported health weight records", extra=core_logger.context(count=self.counts["health_weight"])
            )
        else:
            logger.debug("No health weight data to import")

        # Import health targets
        if health_targets_data:
            for target_data in health_targets_data:
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

                # Only the editable fields: the export also carries the row's id, owner and version.
                editable = health_targets_schema.HealthTargetsUpdate.model_fields
                try:
                    target = health_targets_schema.HealthTargetsUpdate(
                        **{key: value for key, value in target_data.items() if key in editable}
                    )
                except ValidationError:
                    logger.warning("Skipped invalid health targets")
                    continue
                health_targets_integration.edit_health_targets(target, self.user_id, self.db)
                self.counts["health_targets"] += 1
            logger.debug("Imported health targets", extra=core_logger.context(count=self.counts["health_targets"]))
        else:
            logger.debug("No health targets to import")

    async def collect_and_import_health_records(self, records: dict[str, list[Any]]) -> None:
        """Import sleep, steps, water, fasting and poop records.

        Args:
            records: The exported rows of each kind, keyed by kind (``health_sleep``, ...).
        """
        for name, rows in records.items():
            schema, stage = _HEALTH_RECORD_IMPORTS[name]
            for row in rows:
                try:
                    record = schema.model_validate(_without_row_identity(row))
                except ValidationError:
                    logger.warning("Skipped an invalid health record", extra=core_logger.context(kind=name))
                    continue
                if stage(self.user_id, record, self.db):
                    self.counts[name] += 1
            logger.debug("Imported health records", extra=core_logger.context(kind=name, count=self.counts[name]))

    async def add_activity_files_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
        activities_id_mapping: dict[int, int],
    ) -> None:
        """Extract and import activity files from ZIP.

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
                except ValueError:
                    logger.debug(
                        "Skipped an archive file without an activity id", extra=core_logger.context(file_path=path)
                    )
                    continue
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
                except core_exceptions.DomainError as err:
                    logger.warning(
                        "Profile import dropped an invalid activity file",
                        extra=core_logger.context(file_name=new_file_name, detail=err.detail),
                    )
                    continue
                await asyncio.to_thread(
                    activity_file_storage_integration.store_activity_file,
                    new_id,
                    ext,
                    file_bytes,
                    self.storage,
                )
                self.counts["activity_files"] += 1

    async def add_activity_media_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
        activities_id_mapping: dict[int, int],
    ) -> None:
        """Extract and import activity media from ZIP.

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
                    except ValueError:
                        logger.debug(
                            "Skipped an archive file without an activity id", extra=core_logger.context(file_path=path)
                        )
                        continue
                    new_id = activities_id_mapping.get(orig_id_int)

                    if new_id is None:
                        continue

                    new_file_name = f"{new_id}_{suffix}{ext}"

                    # Read bytes from ZIP and validate them as an image
                    # before storing, then write through the platform
                    # StorageProvider under the media area (the same place
                    # an upload lands) rather than to a local directory.
                    image_limit = file_uploads.file_validator.config.limits.max_image_size
                    file_bytes = self._read_zip_entry(zipf, file_path, max_bytes=image_limit)
                    try:
                        await file_uploads.validate_bytes(
                            file_bytes,
                            kind=file_uploads.UploadKind.IMAGE,
                            filename=new_file_name,
                        )
                    except core_exceptions.DomainError as err:
                        logger.warning(
                            "Profile import dropped invalid activity media",
                            extra=core_logger.context(file_name=new_file_name, detail=err.detail),
                        )
                        continue
                    await asyncio.to_thread(
                        activity_media_integration.store_media_blob,
                        new_id,
                        suffix,
                        ext,
                        file_bytes,
                        self.storage,
                    )
                    self.counts["media"] += 1

    async def add_user_images_from_zip(
        self,
        zipf: zipfile.ZipFile,
        file_list: set,
    ) -> None:
        """Extract and import user images from ZIP.

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
            if path.lower().endswith(tuple(users_constants.ALLOWED_USER_IMAGE_EXTENSIONS)) and path.startswith(
                "user_images/"
            ):
                logger.debug("Processing a user image file", extra=core_logger.context(file_path=file_path))
                ext = os.path.splitext(path)[1].lower()
                new_file_name = f"{self.user_id}{ext}"

                # Read bytes from ZIP and save through the unified
                # validated-write pipeline so the entry is re-checked
                # as an image.
                image_limit = file_uploads.file_validator.config.limits.max_image_size
                file_bytes = self._read_zip_entry(zipf, file_path, max_bytes=image_limit)
                try:
                    await file_uploads.validate_bytes(
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
                await asyncio.to_thread(
                    users_integration.store_user_photo, self.user_id, ext, file_bytes, self.storage, self.db
                )
                self.counts["user_images"] += 1
