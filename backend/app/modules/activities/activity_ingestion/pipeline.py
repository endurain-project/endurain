"""The ingestion pipeline: validate -> parse -> enrich -> store -> retain.

One path, shared by every source. The entry points in :mod:`upload_entry` and
:mod:`bulk_entry` differ only in how they obtain the file and what they do when
this fails; everything between a validated file on disk and persisted activities
lives here.

The pipeline is format-agnostic. It asks
:mod:`~modules.activities.activity_file_import.registry` for the parser
registered to the extension and iterates whatever activities come back — a
multi-session ``.fit`` is not special-cased, because the registry hands back the
same :class:`~modules.activities.activity.contracts.ParsedFile` shape for every
format. Keeping this module (rather than ``activity/``) responsible for parsing
is what lets the activities core stay parser-agnostic — see the
``activities-parsing-boundary`` import-linter contract.
"""

import contextlib
import gzip
import os
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_file_import.registry as parser_registry
import modules.activities.activity_file_storage.service as activity_file_storage_service
import modules.activities.activity_ingestion.enrichment as enrichment
import modules.activities.activity_ingestion.sources as ingestion_sources
import modules.strava.bulk_import_utils as strava_bulk_import_utils
import modules.users.users.crud as users_crud
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud

logger = core_logger.get_logger(__name__)


def parse_file(
    token_user_id: int,
    file_extension: str,
    filename: str,
    activity_name: str | None = None,
    default_timezone: str | None = None,
) -> activities_contracts.ParsedFile | None:
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
        HTTPException: 406 when no parser is registered for the extension, 500 on
            a parse failure.
    """
    try:
        if filename.lower() == "bulk_import/__init__.py":
            return None

        logger.info(f"Parsing file: {Path(filename).name}")
        # Dispatch to the parser registered for this extension. The parsers
        # are pure (no db / privacy / gear / provider coupling); the
        # pipeline re-attaches that domain context afterwards — including
        # the owner's timezone, which the parsers cannot look up themselves.
        parser = parser_registry.get_parser(file_extension)
        if parser is None:
            supported = ", ".join(parser_registry.supported_extensions())
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"File extension not supported. Supported file extensions are {supported}",
            )
        return parser(filename, token_user_id, activity_name, default_timezone)
    except HTTPException as http_err:
        raise http_err
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        # Log the exception with full traceback but return a generic
        # error message to the caller to avoid internal info disclosure.
        logger.error(f"Error in parse_file - {err}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def _retain_source_file(
    file_path: str,
    file_extension: str,
    activity_ids: list[int],
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
    """
    if activity_ids:
        with open(file_path, "rb") as source_file:
            file_bytes = source_file.read()
        activity_file_storage_service.store_activity_file_for_ids(
            activity_ids,
            file_extension,
            file_bytes,
            platform_runtime.get_active_platform().storage,
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
    source: ingestion_sources.IngestionSource,
    garmin_connect_activity_id: str | None = None,
) -> list[activities_schema.Activity] | None:
    """Parse a validated, on-disk activity file and persist its activities.

    The single ingestion core shared by every source. By the time it runs the file
    has already been validated and (if it was a ``.gz``) decompressed by the
    calling entry point, so it only resolves the owner, parses the file, enriches
    and persists each activity, retains the source file, and imports any Strava
    bulk-export media.

    It has a single failure contract: it **raises** on any error. The thin entry
    points adapt that to their own contract (the upload entry cleans up and
    re-raises; the bulk entry moves the file to the error directory and returns
    ``None``).

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the (already validated/decompressed) file.
        file_extension: The file's extension (e.g. ``.gpx``/``.fit``).
        file_base_name: Original base filename (pre-decompression) — the key into
            the Strava bulk-import metadata.
        db: SQLAlchemy database session.
        source: Where the file came from, and any source-specific metadata.
        garmin_connect_activity_id: Garmin Connect activity id parsed from the
            filename, for a Garmin sync.

    Returns:
        List of created activity schemas, or ``None`` if the file yielded no
        parseable activity.

    Raises:
        HTTPException: When the user (or privacy settings) cannot be found, or on
            an internal parse/persist failure.
    """
    user = users_crud.get_user_by_id(token_user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
    if user_privacy_settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User privacy settings not found",
        )

    from_garmin = isinstance(source, ingestion_sources.GarminSource)
    bulk_source = source if isinstance(source, ingestion_sources.BulkImportSource) else None
    activity_name = source.activity_name if not isinstance(source, ingestion_sources.BulkImportSource) else None

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

    # Persist the file's exercise-title reference rows (parsed as data — the
    # parser no longer writes them). File-scoped, so this happens once.
    if parsed_file.exercise_titles:
        activity_exercise_titles_crud.create_activity_exercise_titles(parsed_file.exercise_titles, db)

    # Supplemental metadata from a bulk import's manifest, when there is one.
    activity_metadata = bulk_source.metadata_for(file_base_name) if bulk_source else {}

    # File-based sources (direct upload, generic + Strava bulk import) carry no
    # provider activity id, so their stable identity for idempotency is the
    # SHA-256 of the (already-decompressed) file. Garmin syncs key off the
    # provider id instead, so skip the hash there.
    import_source = activities_contracts.ImportSource(
        kind=source.kind,
        content_hash=None if from_garmin else core_file_uploads.sha256_file(file_path),
    )
    garmin_activity_id = int(garmin_connect_activity_id) if garmin_connect_activity_id else None

    created_activities: list[activities_schema.Activity] = []
    for parsed in parsed_file.activities:
        # Re-attach owner privacy defaults, gear, and Garmin ids before the
        # bulk-import metadata can override the gear.
        enrichment.enrich_parsed_activity(
            parsed.activity,
            user_id=token_user_id,
            user_privacy_settings=user_privacy_settings,
            db=db,
            from_garmin=from_garmin,
            garminconnect_gear=source.gear if from_garmin else None,
            garmin_connect_activity_id=garmin_activity_id,
        )

        if bulk_source is not None:
            if not bulk_source.should_import(
                parsed.activity,
                activity_metadata,
                activities_in_file=len(parsed_file.activities),
            ):
                continue
            strava_bulk_import_utils.apply_bulk_import_metadata(parsed.activity, activity_metadata)

        parsed.source = import_source
        created_activities.append(ingestion_service.store_parsed_activity(parsed, db))

    _retain_source_file(
        file_path,
        file_extension,
        [activity.id for activity in created_activities if activity.id is not None],
    )

    if bulk_source is not None:
        _finish_bulk_import_file(bulk_source, created_activities, file_base_name, db)

    return created_activities


def _finish_bulk_import_file(
    source: ingestion_sources.BulkImportSource,
    created_activities: list[activities_schema.Activity],
    file_base_name: str,
    db: Session,
) -> None:
    """Log completion of one bulk-import file and import its Strava media.

    Args:
        source: The bulk-import source, carrying the Strava export metadata.
        created_activities: Activities persisted from the file.
        file_base_name: The file's original base name.
        db: Database session.
    """
    ids_to_filename = "_".join(str(activity.id) for activity in created_activities)
    logger.info(
        f"Bulk file import: file {file_base_name} successfully processed and stored for activities {ids_to_filename}",
        extra=core_logger.context(console=True),
    )

    # Deal with Strava bulk import media. Note - even multi-activity .fit files
    # are good with this code, as there should only be a single imported activity
    # per file in the Strava activities file directory.
    if source.strava_activities and created_activities:
        strava_bulk_import_utils.import_media_from_strava_bulk_export(
            source.strava_activities,
            created_activities[-1],
            file_base_name,
            db,
        )

    logger.info(
        f"Bulk file import: Import work complete for file {file_base_name}.",
        extra=core_logger.context(console=True),
    )


def validate_prepare_and_store_file(
    token_user_id: int,
    file_path: str,
    db: Session,
    *,
    source: ingestion_sources.IngestionSource,
) -> list[activities_schema.Activity] | None:
    """Validate, decompress, and store one on-disk activity file — **raising** on failure.

    The shared raising core behind both the swallowing background entry
    (:func:`~modules.activities.activity_ingestion.bulk_entry.store_activity_file`,
    which moves the file to the error dir and returns ``None``) and the durable
    bulk-import job body
    (:func:`~modules.activities.activity_ingestion.bulk_entry.store_bulk_import_file`,
    which lets the failure propagate so the job runner retries and eventually
    dead-letters). Does no error-directory handling itself — the caller owns the
    failure policy.

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the activity file to parse.
        db: SQLAlchemy database session.
        source: Where the file came from, and any source-specific metadata.

    Returns:
        List of created activity schema objects.

    Raises:
        HTTPException: 406 for an unsupported extension, 400 when a ``.gz``
            decompresses to an unsupported payload.
    """
    _, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()

    if file_extension not in core_config.SUPPORTED_FILE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=("File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"),
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
    if isinstance(source, ingestion_sources.GarminSource):
        garmin_connect_activity_id = os.path.basename(file_path).split("_")[0]

    if file_extension == ".gz":
        file_path, file_extension = core_file_uploads.decompress_gzip(file_path)
        file_extension = file_extension.lower()
        if file_extension not in core_config.SUPPORTED_FILE_FORMATS or file_extension == ".gz":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("Decompressed file extension is not supported"),
            )
        core_file_uploads.validate_local_file_sync(
            file_path,
            kind=core_file_uploads.UploadKind.ACTIVITY,
        )

    return store_activities_from_file(
        token_user_id,
        file_path,
        file_extension,
        file_base_name,
        db,
        source=source,
        garmin_connect_activity_id=garmin_connect_activity_id,
    )
