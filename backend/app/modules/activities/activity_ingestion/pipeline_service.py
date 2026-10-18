"""The ingestion pipeline: validate -> parse -> enrich -> store -> retain.

One path, shared by every source. The entry points in :mod:`upload_entry_service`,
:mod:`provider_entry_service` and :mod:`bulk_import_service` differ only in how they
obtain the file and what they do when this fails; everything between a validated file
on disk and persisted activities lives here.

The pipeline is format-agnostic. It asks
:mod:`~modules.activities.activity_file_import.parser_registry` for the parser
registered to the extension and iterates whatever activities come back — a
multi-session ``.fit`` is not special-cased, because the registry hands back the
same :class:`~modules.activities.activity.contracts.ParsedFile` shape for every
format. It is **provider-agnostic** too: everything a specific origin knows
(Strava export metadata, its sidecar photos, which duplicate listings to skip)
is answered by the :mod:`sources` object it was handed, never by branching on the
provider here. Keeping this module (rather than ``activity/``) responsible for
parsing is what lets the activities core stay parser-agnostic — see the
``activities-parsing-boundary`` and ``ingestion-pipeline-provider-agnostic``
import-linter contracts.
"""

import contextlib
import gzip
import os
from pathlib import Path

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_import.integration_service as activity_file_import_integration
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.enrichment_service as activity_ingestion_enrichment_service
import modules.activities.contributor_registry as activities_contributor_registry
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def parse_file(
    token_user_id: int,
    file_extension: str,
    filename: str,
    activity_name: str | None = None,
    default_timezone: str | None = None,
) -> activity_contracts.ParsedFile | None:
    """Parse one activity file into its activities.

    Args:
        token_user_id: ID of the user the parsed activities will belong to.
        file_extension: The file's extension, e.g. ``".fit"``.
        filename: Absolute path to the file to parse.
        activity_name: Optional override for the parsed activity's name.
        default_timezone: The owner's IANA timezone, used only when the file
            yields no timezone of its own.

    Returns:
        The parsed file, or ``None`` for the bulk-import package marker file.

    Raises:
        UnsupportedFormatError: When no parser is registered for the extension.
        ProcessingError: On a parse failure.
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
        return parser(filename, token_user_id, activity_name, default_timezone or core_config.settings.TZ)
    except core_exceptions.DomainError:
        raise
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        # Log the exception with full traceback but return a generic
        # error message to the caller to avoid internal info disclosure.
        logger.error(
            "Error in parse_file",
            exc_info=err,
            extra=core_logger.context(file=Path(filename).name, user_id=token_user_id),
        )
        raise core_exceptions.ProcessingError() from err


def _retain_source_file(
    file_path: str,
    file_extension: str,
    activity_ids: list[int],
    storage: platform_providers.StorageProvider,
) -> None:
    """Persist the source file against each activity parsed from it, then consume it.

    Written through the platform ``StorageProvider`` — the same abstraction
    thumbnails use — so file-based ingestion works unchanged on local disk or
    object storage instead of being pinned to this node's disk. Each activity owns
    its own copy keyed by id, so its lifecycle (profile export, deletion) is
    independent, including the several activities parsed from a single
    multi-activity ``.fit``.

    Args:
        file_path: The parsed file on disk. Removed afterwards.
        file_extension: The file's extension, used for the stored object's name.
        activity_ids: IDs of the activities parsed from the file.
        storage: The blob-storage provider the file is retained in.
    """
    if activity_ids:
        with open(file_path, "rb") as source_file:
            file_bytes = source_file.read()
        activity_file_storage_integration.store_activity_file_for_ids(
            activity_ids,
            file_extension,
            file_bytes,
            storage,
        )

    with contextlib.suppress(OSError):
        os.remove(file_path)


def store_activities_from_file(
    token_user_id: int,
    file_path: str,
    file_extension: str,
    file_base_name: str,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
    storage: platform_providers.StorageProvider,
    garmin_connect_activity_id: str | None = None,
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
        garmin_connect_activity_id: Garmin Connect activity id parsed from the
            filename, for a Garmin sync.

    Returns:
        List of created activity schemas, or ``None`` if the file yielded no
        parseable activity.

    Raises:
        NotFoundError: When the user (or their privacy settings) cannot be found.
        ProcessingError: On an internal parse/persist failure.
    """
    user = users_integration.get_user(token_user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")

    user_privacy_settings = users_integration.get_privacy_settings(user.id, db)
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

    # CPU-bound + sync I/O parsing (gpxpy, geopy, timezonefinder). This runs
    # directly: every entry point reaches here on a worker thread (a sync route
    # on Starlette's threadpool, the bulk-import ThreadPoolExecutor, or
    # ``asyncio.to_thread`` from the Garmin sync), never on the main event loop.
    parsed_file = parse_file(
        token_user_id,
        file_extension,
        file_path,
        activity_name,
        # Only consulted when the file yields no timezone of its own. Without it
        # a GPS-less activity (treadmill, turbo, pool) inherits the *server's*
        # timezone, which is meaningless for an athlete on another continent.
        user.timezone,
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
            logger.error(
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
    import_source = activity_contracts.ImportSource(
        kind=source.kind,
        content_hash=None if garmin_source else core_file_uploads.sha256_file(file_path),
    )
    garmin_activity_id = int(garmin_connect_activity_id) if garmin_connect_activity_id else None

    created_activities: list[activity_schema.ActivityRead] = []
    for parsed in parsed_file.activities:
        # Re-attach owner privacy defaults, gear, and Garmin ids before the
        # bulk-import metadata can override the gear.
        activity_ingestion_enrichment_service.enrich_parsed_activity(
            parsed.activity,
            user_id=token_user_id,
            user_privacy_settings=user_privacy_settings,
            db=db,
            from_garmin=garmin_source is not None,
            # Read through the narrowed source rather than a separate boolean:
            # only ``GarminSource`` carries gear, and a plain ``from_garmin``
            # flag left that unprovable (and one refactor away from an
            # AttributeError on the other two source types).
            provider_gear_id=garmin_source.gear_id if garmin_source else None,
            garminconnect_gear_id=garmin_source.provider_gear_id if garmin_source else None,
            garmin_connect_activity_id=garmin_activity_id,
        )

        if bulk_source is not None:
            if not bulk_source.should_import(
                parsed.activity,
                activity_metadata,
                activities_in_file=len(parsed_file.activities),
            ):
                continue
            bulk_source.apply_metadata(parsed.activity, activity_metadata)

        parsed.source = import_source
        created_activities.append(activity_integration.store_parsed_activity(parsed, db))
        # One commit per activity: the row, its components and the event land
        # together, and a later file failing does not undo this one.
        db.commit()

    _retain_source_file(
        file_path,
        file_extension,
        [activity.id for activity in created_activities if activity.id is not None],
        storage,
    )

    if bulk_source is not None:
        _finish_bulk_import_file(bulk_source, created_activities, file_base_name, db)

    return created_activities


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
    token_user_id: int,
    file_path: str,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
    storage: platform_providers.StorageProvider,
) -> list[activity_schema.ActivityRead] | None:
    """Validate, decompress, and store one on-disk activity file — **raising** on failure.

    The shared raising core behind the swallowing provider entry
    (:func:`~modules.activities.activity_ingestion.provider_entry_service.store_activity_file`,
    which logs and returns ``None``) and the bulk import's per-file step, which
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
    # (pre-decompression) base filename, and the Garmin activity id is parsed
    # from it — capture both before any ``.gz`` handling rewrites the path.
    _, file_base_name = os.path.split(file_path)

    garmin_connect_activity_id = None
    if isinstance(source, activity_ingestion_contracts.GarminSource):
        garmin_connect_activity_id = os.path.basename(file_path).split("_")[0]

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
            garmin_connect_activity_id=garmin_connect_activity_id,
        )
        if decompressed_path is not None:
            # The archive is consumed only once its contents are imported, so a
            # failure leaves it for the caller to deal with.
            core_file_uploads.remove_files([original_path])
        return created
    finally:
        if decompressed_path is not None:
            core_file_uploads.remove_files([decompressed_path])
