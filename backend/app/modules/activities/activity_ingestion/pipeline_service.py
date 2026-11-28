"""The ingestion pipeline: validate -> parse -> enrich -> retain -> store.

One path, shared by every source. The entry points in :mod:`upload_entry_service`,
:mod:`provider_entry_service` and :mod:`bulk_import_service` differ only in how they
obtain the file and what they do when this fails; everything between a validated file
on disk and persisted activities lives here.

The pipeline is format-agnostic. It asks
:mod:`~modules.activities.activity_file_import.parser_registry` for the parser
registered to the extension and stores whatever comes back: the registry hands
back the same :class:`~modules.activities.activity.contracts.ParsedFile` shape for
every format, its activities and, for a multisport file, the parent they are the
legs of. It is **provider-agnostic** too: everything a specific origin knows
(Strava export metadata, its sidecar photos, which duplicate listings to skip)
is answered by the :mod:`sources` object it was handed, never by branching on the
provider here. Keeping this module (rather than ``activity/``) responsible for
parsing is what lets the activities core stay parser-agnostic — see the
``activities-parsing-boundary`` and ``ingestion-pipeline-format-agnostic``
import-linter contracts.
"""

import contextlib
import dataclasses
import gzip
import os
import uuid
from pathlib import Path

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_import.integration_service as activity_file_import_integration
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.enrichment_service as activity_ingestion_enrichment_service
import modules.activities.contributor_registry as activities_contributor_registry
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration

logger = core_logger.get_logger(__name__)


def parse_file(
    token_user_id: uuid.UUID,
    file_extension: str,
    filename: str,
    activity_name: str | None = None,
    default_timezone: str | None = None,
    units: server_settings_schema.Units = server_settings_schema.Units.METRIC,
) -> activity_contracts.ParsedFile | None:
    """Parse one activity file into its activities.

    Args:
        token_user_id: ID of the user the parsed activities will belong to.
        file_extension: The file's extension, e.g. ``".fit"``.
        filename: Absolute path to the file to parse.
        activity_name: Optional override for the parsed activity's name.
        default_timezone: The owner's IANA timezone, used only when the file
            yields no timezone of its own.
        units: The owner's measurement units; they set the length of an automatic lap
            for formats that carry no device laps.

    Returns:
        The parsed file, or ``None`` for the bulk-import package marker file.

    Raises:
        UnsupportedFormatError: When no parser is registered for the extension.
        InvalidInputError: When the file's content cannot be parsed.
        ProcessingError: When the file cannot be read.
    """
    try:
        if filename.lower() == "bulk_import/__init__.py":
            return None

        logger.debug(
            "Parsing activity file", extra=core_logger.context(file=Path(filename).name, user_id=token_user_id)
        )
        # Dispatch to the parser registered for this extension. The parsers
        # are pure (no db / privacy / gear / provider coupling); the
        # pipeline re-attaches that domain context afterwards — including
        # the owner's timezone, which the parsers cannot look up themselves.
        parser = activity_file_import_integration.get_parser(file_extension)
        if parser is None:
            supported = ", ".join(activity_file_import_integration.supported_extensions())
            raise core_exceptions.UnsupportedFormatError(
                f"File extension not supported. Supported file extensions are {supported}"
            )
        # The parsers are pure and cannot read settings, so the server timezone
        # fallback for a file with no zone of its own is applied here.
        lap_distance_km = activity_file_import_integration.auto_lap_distance_km(
            units is server_settings_schema.Units.IMPERIAL
        )
        return parser(
            filename, token_user_id, activity_name, default_timezone or core_config.settings.TZ, lap_distance_km
        )
    except core_exceptions.DomainError:
        raise
    except (EOFError, gzip.BadGzipFile, ValueError, KeyError, TypeError) as err:
        # The file's content broke the parser: every retry reaches the same verdict, so the upload ends as
        # an invalid file. The traceback is kept at WARNING in case the parser itself is at fault.
        logger.warning(
            "Could not parse an activity file",
            exc_info=err,
            extra=core_logger.context(file=Path(filename).name, user_id=token_user_id),
        )
        raise core_exceptions.InvalidInputError("The activity file could not be read") from err
    except (OSError, RuntimeError) as err:
        # Server-side and possibly transient; the job runner logs it with this context's traceback.
        logger.debug(
            "Failed to read an activity file",
            exc_info=err,
            extra=core_logger.context(file=Path(filename).name, user_id=token_user_id),
        )
        raise core_exceptions.ProcessingError() from err


class _RetainedFile:
    """The source file of one ingestion, staged as a retained file row when the first activity is about to be stored.

    Staging waits for the first activity that will be stored, so a file that yields nothing, or whose activities a
    bulk source skips, leaves no row. One row serves every activity of a multi-activity file.

    Attributes:
        file_id: The staged row's id, ``None`` until :meth:`stage` ran.
        created: Whether this ingestion created the row.
        attached: Whether an activity of this ingestion references the row.
    """

    def __init__(
        self,
        user_id: uuid.UUID,
        file_path: str,
        file_extension: str,
        sha256: str,
        storage: platform_providers.StorageProvider,
    ) -> None:
        """Describe the file to stage.

        Args:
            user_id: The owner.
            file_path: The parsed file on disk.
            file_extension: The file's extension, e.g. ``".fit"``.
            sha256: Hex SHA-256 of the file.
            storage: The blob-storage provider.
        """
        self._user_id = user_id
        self._file_path = file_path
        self._file_extension = file_extension
        self._sha256 = sha256
        self._storage = storage
        self.file_id: uuid.UUID | None = None
        self.created = False
        self.attached = False

    def stage(self, db: Session) -> uuid.UUID:
        """Return the file row's id, staging the row and storing the blob on the first call.

        Args:
            db: The ingestion's session; its open transaction ends first, so no session is open across the blob write.

        Returns:
            The file row's id.
        """
        if self.file_id is None:
            db.commit()
            with open(self._file_path, "rb") as source_file:
                file_bytes = source_file.read()
            staged = activity_file_storage_integration.stage_file(
                self._user_id, self._sha256, self._file_extension, file_bytes, self._storage
            )
            self.file_id = staged.ref.file_id
            self.created = staged.created
            logger.debug(
                "Staged the source file of an ingestion",
                extra=core_logger.context(file_id=self.file_id, user_id=self._user_id, created=self.created),
            )
        return self.file_id

    def attach_if_referenced(self, db: Session) -> None:
        """Mark the row attached when an activity staged in this transaction references it.

        A duplicate import stages no activity, so it leaves the row as it found it.

        Args:
            db: The ingestion's session, in the transaction that stored the activity.
        """
        if self.file_id is not None and activity_integration.filter_referenced_file_ids([self.file_id], db):
            activity_file_storage_integration.mark_attached(self.file_id, db)
            self.attached = True

    def release_if_unused(self, db: Session) -> None:
        """Remove the row this ingestion created when no activity ended up referencing it.

        Args:
            db: The ingestion's session; its open transaction ends first.
        """
        if self.file_id is not None and self.created and not self.attached:
            db.commit()
            activity_file_storage_integration.release_unattached(self.file_id, self._storage)
            logger.debug(
                "Released the source file of an ingestion that stored no activity",
                extra=core_logger.context(file_id=self.file_id, user_id=self._user_id),
            )

    def consume(self) -> None:
        """Remove the file from disk, now that it is stored or not wanted."""
        with contextlib.suppress(OSError):
            os.remove(self._file_path)


def store_activities_from_file(
    token_user_id: uuid.UUID,
    file_path: str,
    file_extension: str,
    file_base_name: str,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
    storage: platform_providers.StorageProvider,
) -> list[activity_schema.ActivityRead] | None:
    """Parse a validated, on-disk activity file and persist its activities.

    The single ingestion core shared by every source. By the time it runs the file
    has already been validated and (if it was a ``.gz``) decompressed by the
    calling entry point, so it only resolves the owner, parses the file, enriches
    and persists each activity, retains the source file, and imports any Strava
    bulk-export media.

    It has a single failure contract: it **raises** on any error. The thin entry
    points adapt that to their own contract (the upload entry cleans up and
    re-raises; the provider entry logs and returns ``None``; a bulk import counts
    the failure and keeps the file).

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the (already validated/decompressed) file.
        file_extension: The file's extension (e.g. ``.gpx``/``.fit``).
        file_base_name: Original base filename (pre-decompression) — the key into
            the Strava bulk-import metadata.
        db: SQLAlchemy database session.
        source: Where the file came from, and any source-specific metadata.
        storage: The blob-storage provider the source file is retained in.

    Returns:
        The top-level activities stored from the file: a multisport file's parent
        rather than its legs, except a file whose legs were stored on their own
        before groups existed, which returns those legs. ``None`` if the file
        yielded no parseable activity.

    Raises:
        NotFoundError: When the user (or their privacy settings) cannot be found.
        ProcessingError: On an internal parse/persist failure.
    """
    user = users_integration.get_user(token_user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    user_privacy_settings = users_privacy_settings_integration.get_privacy_settings(user.id, db)
    if user_privacy_settings is None:
        raise core_exceptions.NotFoundError("User privacy settings not found")

    garmin_source = source if isinstance(source, activity_ingestion_contracts.GarminSource) else None
    bulk_source = source if isinstance(source, activity_ingestion_contracts.BulkImportSource) else None
    activity_name = (
        source.activity_name if not isinstance(source, activity_ingestion_contracts.BulkImportSource) else None
    )

    # Parsing takes seconds; end the read transaction so the connection goes back
    # to the pool instead of idling in it.
    db.commit()

    # CPU-bound and sync I/O parsing runs directly: every entry point reaches
    # here on a worker thread (a sync route on Starlette's threadpool, the
    # ingestion worker pool, or a durable job), never on the event loop.
    parsed_file = parse_file(
        token_user_id,
        file_extension,
        file_path,
        activity_name,
        # Only consulted when the file yields no timezone of its own. Without it
        # a GPS-less activity (treadmill, turbo, pool) inherits the *server's*
        # timezone, which is meaningless for an athlete on another continent.
        user.timezone,
        server_settings_schema.Units(user.units),
    )

    if parsed_file is None:
        return None

    # Note: a file that parses but yields no activities is *not* an early return.
    # It still falls through to the retention step below, which consumes the
    # staged input — returning here would leak the temp file into the import
    # directory and have the next run pick it up again.

    file_component_work = []
    for key, data in parsed_file.components.items():
        if data is None:
            continue
        contributor = activities_contributor_registry.get_file_ingestion_contributor(key)
        if contributor is None:
            logger.debug(
                "No file ingestion contributor is registered for a parsed component",
                extra=core_logger.context(component=key),
            )
            raise core_exceptions.ProcessingError()
        file_component_work.append((contributor, data))

    for contributor, data in file_component_work:
        contributor.persist(data, db)
    if file_component_work:
        # File-scoped reference data is committed on its own, ahead of the
        # per-activity unit of work.
        db.commit()
        logger.debug(
            "Committed file-scoped reference data",
            extra=core_logger.context(components=len(file_component_work)),
        )

    # Supplemental metadata from a bulk import's manifest, when there is one.
    activity_metadata = bulk_source.metadata_for(file_base_name) if bulk_source else {}

    # File-based sources (direct upload, generic + Strava bulk import) carry no
    # provider activity id, so their stable identity for idempotency is the
    # SHA-256 of the (already-decompressed) file. Garmin syncs key off the
    # provider id instead, so skip the hash there.
    file_sha256 = core_file_uploads.sha256_file(file_path)
    import_source = activity_contracts.ImportSource(
        kind=source.kind,
        content_hash=None if garmin_source else file_sha256,
        precedence=activity_constants.file_source_precedence(file_extension),
    )
    retained = _RetainedFile(token_user_id, file_path, file_extension, file_sha256, storage)
    garmin_activity_id = garmin_source.activity_id if garmin_source else None

    def enrich(
        parsed: activity_contracts.ParsedActivity,
        gear: activity_ingestion_contracts.LegGear,
    ) -> None:
        """Re-attach owner privacy defaults, gear, and Garmin ids to one parsed activity, in place.

        Done before the bulk-import metadata can override the gear.

        Args:
            parsed: The parsed activity, a multisport parent or leg included.
            gear: The gear the source resolved for it.
        """
        activity_ingestion_enrichment_service.enrich_parsed_activity(
            parsed.activity,
            user_id=token_user_id,
            user_privacy_settings=user_privacy_settings,
            db=db,
            from_garmin=garmin_source is not None,
            provider_gear_id=gear.gear_id,
            garminconnect_gear_id=gear.provider_gear_id,
            garmin_connect_activity_id=garmin_activity_id,
        )

    # What the athlete sees of the file: a multisport file's parent, not its legs.
    created_activities: list[activity_schema.ActivityRead] = []
    if parsed_file.parent is not None:
        parent = parsed_file.parent
        no_gear = activity_ingestion_contracts.LegGear()
        enrich(parent, no_gear)
        leg_gear = _leg_gear(garmin_source, len(parsed_file.activities))
        for leg, gear in zip(parsed_file.activities, leg_gear, strict=True):
            enrich(leg, gear)
        # A Strava export ships one copy of the file per leg, each listed at its leg's start. Asking about the parent
        # imports the group from the one copy listed at the parent's start and skips the other copies.
        if bulk_source is None or bulk_source.should_import(
            parent.activity, activity_metadata, activities_in_file=len(parsed_file.activities)
        ):
            if bulk_source is not None:
                bulk_source.apply_metadata(parent.activity, activity_metadata)
            parent.source = dataclasses.replace(import_source, retained_file_id=retained.stage(db))
            for leg in parsed_file.activities:
                leg.source = import_source
            created_activities = activity_integration.store_parsed_group(parent, parsed_file.activities, db)
            retained.attach_if_referenced(db)
            # One commit per group: the parent, its legs, the file's attachment and their events land together.
            db.commit()
    else:
        # Read through the narrowed source rather than a separate boolean: only ``GarminSource`` carries gear.
        activity_gear = (
            activity_ingestion_contracts.LegGear(garmin_source.gear_id, garmin_source.provider_gear_id)
            if garmin_source
            else activity_ingestion_contracts.LegGear()
        )
        for parsed in parsed_file.activities:
            enrich(parsed, activity_gear)

            if bulk_source is not None:
                if not bulk_source.should_import(
                    parsed.activity,
                    activity_metadata,
                    activities_in_file=len(parsed_file.activities),
                ):
                    continue
                bulk_source.apply_metadata(parsed.activity, activity_metadata)

            parsed.source = dataclasses.replace(import_source, retained_file_id=retained.stage(db))
            created_activities.append(activity_integration.store_parsed_activity(parsed, db))
            retained.attach_if_referenced(db)
            # One commit per activity: the row, its components, the file's attachment and the event
            # land together, and a later file failing does not undo this one.
            db.commit()

    retained.release_if_unused(db)
    retained.consume()

    if bulk_source is not None:
        _finish_bulk_import_file(bulk_source, created_activities, file_base_name, db)

    return created_activities


def _leg_gear(
    garmin_source: activity_ingestion_contracts.GarminSource | None, leg_count: int
) -> tuple[activity_ingestion_contracts.LegGear, ...]:
    """Pair each leg of a multisport file with the gear the Garmin sync resolved for it.

    Args:
        garmin_source: The Garmin source of the file, when it came from the sync.
        leg_count: How many legs the file holds.

    Returns:
        One entry per leg, in leg order; entries without gear for a file that is not from the sync, or when the
        sync's count differs from the legs' (none at all included, as Garmin then named no legs).
    """
    no_gear = (activity_ingestion_contracts.LegGear(),) * leg_count
    if garmin_source is None:
        return no_gear
    if len(garmin_source.leg_gear) != leg_count:
        logger.warning(
            "Garmin leg gear does not match the legs of the file, so no leg takes Garmin gear",
            extra=core_logger.context(
                activity_id=garmin_source.activity_id,
                leg_gear_count=len(garmin_source.leg_gear),
                leg_count=leg_count,
            ),
        )
        return no_gear
    return garmin_source.leg_gear


def _finish_bulk_import_file(
    source: activity_ingestion_contracts.BulkImportSource,
    created_activities: list[activity_schema.ActivityRead],
    file_base_name: str,
    db: Session,
) -> None:
    """Log completion of one bulk-import file and import its side artifacts.

    Args:
        source: The bulk-import source, which owns any source-specific follow-up.
        created_activities: Activities persisted from the file.
        file_base_name: The file's original base name.
        db: Database session.
    """
    ids_to_filename = "_".join(str(activity.id) for activity in created_activities)
    logger.debug(
        "Bulk file import: file processed and stored",
        extra=core_logger.context(
            file=file_base_name,
            activity_ids=ids_to_filename,
            activity_count=len(created_activities),
        ),
    )

    # Anything that shipped alongside the file rather than inside it (a Strava
    # export's photos today). The source decides what that means — the pipeline
    # stays format- and provider-agnostic.
    source.import_side_artifacts(created_activities, file_base_name, db)


def validate_prepare_and_store_file(
    token_user_id: uuid.UUID,
    file_path: str,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
    storage: platform_providers.StorageProvider,
) -> list[activity_schema.ActivityRead] | None:
    """Validate, decompress, and store one on-disk activity file — **raising** on failure.

    The shared raising core behind the provider entry
    (:func:`~modules.activities.activity_ingestion.provider_entry_service.store_activity_file`,
    which logs a refused file and returns ``None``) and the bulk import's per-file step, which
    counts the failure and keeps the file. Does no failure handling itself — the
    caller owns the policy.

    A ``.gz`` is decompressed to a temp file that is always removed here; the
    ``.gz`` itself is removed only after a successful import.

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the activity file to parse.
        db: SQLAlchemy database session.
        source: Where the file came from, and any source-specific metadata.
        storage: The blob-storage provider the source file is retained in.

    Returns:
        List of created activity schema objects.

    Raises:
        UnsupportedFormatError: For an unsupported extension.
        InvalidInputError: When a ``.gz`` decompresses to an unsupported payload.
    """
    _, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()

    if file_extension not in core_config.SUPPORTED_FILE_FORMATS:
        raise core_exceptions.UnsupportedFormatError(
            "File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"
        )

    # Defense-in-depth signature check on files queued for
    # processing (Garmin / Strava import paths).
    core_file_uploads.validate_local_file_sync(
        file_path,
        kind=(core_file_uploads.UploadKind.GZIP if file_extension == ".gz" else core_file_uploads.UploadKind.ACTIVITY),
    )

    # The Strava bulk-import metadata is keyed by the original
    # (pre-decompression) base filename — capture it before any ``.gz``
    # handling rewrites the path.
    _, file_base_name = os.path.split(file_path)

    original_path = file_path
    decompressed_path: str | None = None
    try:
        if file_extension == ".gz":
            file_path, file_extension = core_file_uploads.decompress_gzip(original_path)
            decompressed_path = file_path
            file_extension = file_extension.lower()
            if file_extension not in core_config.SUPPORTED_FILE_FORMATS or file_extension == ".gz":
                raise core_exceptions.InvalidInputError("Decompressed file extension is not supported")
            core_file_uploads.validate_local_file_sync(
                file_path,
                kind=core_file_uploads.UploadKind.ACTIVITY,
            )

        created = store_activities_from_file(
            token_user_id,
            file_path,
            file_extension,
            file_base_name,
            db,
            source=source,
            storage=storage,
        )
        if decompressed_path is not None:
            # The archive is consumed only once its contents are imported, so a
            # failure leaves it for the caller to deal with.
            core_file_uploads.remove_files([original_path])
        return created
    finally:
        if decompressed_path is not None:
            core_file_uploads.remove_files([decompressed_path])
