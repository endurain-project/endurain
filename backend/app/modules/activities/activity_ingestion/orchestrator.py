"""Orchestrate parsing + persistence of activity files (uploads, Garmin, Strava bulk).

This module owns the file-format-aware ingestion flow that used to live in
``activity/utils.py``. It parses ``.gpx`` / ``.tcx`` / ``.fit`` / ``.gz`` files (delegating
to :mod:`activity_file_import`), adapts each parsed result into the canonical
:class:`~modules.activities.activity.schema.ParsedActivity` via
:mod:`~modules.activities.activity_ingestion.file_adapter`, and persists it through
:func:`modules.activities.activity.ingestion_service.store_parsed_activity`.

Keeping this here (rather than in ``activity/``) is what lets the activities core stay
parser-agnostic — see the ``activities-parsing-boundary`` import-linter contract.
"""

import contextlib
import gzip
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_file_import.registry as parser_registry
import modules.activities.activity_file_import.utils_fit as fit_utils
import modules.activities.activity_file_storage.service as activity_file_storage_service
import modules.activities.activity_ingestion.enrichment as enrichment
import modules.activities.activity_ingestion.file_adapter as file_adapter
import modules.strava.bulk_import_utils as strava_bulk_import_utils
import modules.users.users.crud as users_crud
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud

logger = core_logger.get_logger(__name__)


def _prepare_bulk_import_activity(
    activity: dict,
    is_bulk_import: bool,
    created_activities_objects: list,
    strava_activities: dict | None,
    activity_metadata_dict: dict,
) -> dict | None:
    """Process a single activity for bulk import.

    Returns the (possibly updated) activity, or None if the activity
    should be skipped (e.g. duplicate from a multi-activity .fit file).

    When not a bulk import, returns the activity unchanged.
    """
    if not is_bulk_import:
        return activity

    # For a Strava bulk import of a multi-activity .fit file, check to see
    # if this is the same activity referenced in the activities.csv for
    # this file.
    if (
        len(created_activities_objects) > 1
        and strava_activities
        and activity_metadata_dict["metadata_found_in_csv"] is True
        and not strava_bulk_import_utils.does_activity_start_time_match_the_data_in_strava_activities_csv(
            activity, activity_metadata_dict
        )
    ):
        # This activity does not match the Strava CSV entry — skip import.
        logger.debug(
            "Bulk activity import of multi-activity .fit file: "
            "skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file "
            "in the Strava activities.csv file.",
            extra=core_logger.context(console=True),
        )
        return None

    # Add import metadata and Strava activities.csv metadata
    activity = strava_bulk_import_utils.append_bulk_import_metadata_to_activity(activity, activity_metadata_dict)
    return activity


def parse_file(
    token_user_id: int,
    file_extension: str,
    filename: str,
    activity_name: str | None = None,
    default_timezone: str | None = None,
) -> dict | None:
    try:
        if filename.lower() != "bulk_import/__init__.py":
            logger.info(f"Parsing file: {Path(filename).name}")
            # Dispatch to the parser registered for this extension. The parsers
            # are pure (no db / privacy / gear / provider coupling); the
            # orchestrator re-attaches that domain context afterwards — including
            # the owner's timezone, which the parsers cannot look up themselves.
            parser = parser_registry.get_parser(file_extension)
            if parser is None:
                supported = ", ".join(parser_registry.supported_extensions())
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail=f"File extension not supported. Supported file extensions are {supported}",
                )
            return parser(filename, token_user_id, activity_name, default_timezone)
        else:
            return None
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


def _store_activities_from_file(
    token_user_id: int,
    file_path: str,
    file_extension: str,
    file_base_name: str,
    db: Session,
    *,
    from_garmin: bool = False,
    is_bulk_import: bool = False,
    garminconnect_gear: dict | None = None,
    strava_activities: dict | None = None,
    import_initiated_time: str | None = None,
    users_existing_gear_nickname_to_id: dict | None = None,
    garmin_connect_activity_id: str | None = None,
    activity_name: str | None = None,
) -> list[activities_schema.Activity] | None:
    """Parse a validated, on-disk activity file and persist its activities.

    This is the single ingestion core shared by every source (direct upload,
    Garmin sync, Strava/generic bulk import). By the time it runs the file has
    already been validated and (if it was a ``.gz``) decompressed by the calling
    entry point, so it only resolves the owner, parses the file, persists each
    activity via ``ingestion_service.store_parsed_activity``, moves the file into
    the processed directory, and imports any Strava bulk-export media.

    It has a single failure contract: it **raises** on any error. The thin entry
    points adapt that to their own contract (the upload entry cleans up and
    re-raises; the bulk/provider entry moves the file to the error directory and
    returns ``None``).

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the (already validated/decompressed) file.
        file_extension: The file's extension (e.g. ``.gpx``/``.fit``).
        file_base_name: Original base filename (pre-decompression) — the key into
            the Strava bulk-import metadata dict.
        db: SQLAlchemy database session.
        from_garmin: Whether the file originates from a Garmin Connect sync.
        is_bulk_import: Whether this is part of a bulk import.
        garminconnect_gear: Garmin Connect gear metadata to associate.
        strava_activities: Strava bulk-import metadata dict keyed by filename.
        import_initiated_time: ISO timestamp of when the bulk import started.
        users_existing_gear_nickname_to_id: Gear nickname -> id map (Strava bulk).
        garmin_connect_activity_id: Garmin Connect activity id parsed from the
            filename, when ``from_garmin``.
        activity_name: Optional override for the activity name.

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

    # CPU-bound + sync I/O parsing (gpxpy, geopy, timezonefinder). This runs
    # directly: every entry point reaches here on a worker thread (a sync route
    # on Starlette's threadpool, the bulk-import ThreadPoolExecutor, or
    # ``asyncio.to_thread`` from the Garmin sync), never on the main event loop.
    parsed_info = parse_file(
        token_user_id,
        file_extension,
        file_path,
        activity_name,
        # Only consulted when the file yields no timezone of its own. Without it
        # a GPS-less activity (treadmill, turbo, pool) inherits the *server's*
        # timezone, which is meaningless for an athlete on another continent.
        user.timezone,
    )

    if parsed_info is None:
        return None

    # Gather supplemental metadata. Check if a Strava bulk import is in
    # progress, and if so check to see if any additional information
    # can be added to the activity.
    activity_metadata_dict = {}
    if strava_activities and isinstance(strava_activities, dict) and import_initiated_time and is_bulk_import:
        # Build a metadata dict (which will also include an
        # import_dict) based on information in the strava_activities
        # dict.
        activity_metadata_dict = strava_bulk_import_utils.build_metadata_dict(
            file_base_name,
            strava_activities,
            import_initiated_time,
            users_existing_gear_nickname_to_id,
        )
    elif import_initiated_time and is_bulk_import:
        # Not doing a Strava bulk import, so build an import info dict
        # that reflects the generic import.
        import_dict = strava_bulk_import_utils.build_import_dictionary(file_base_name, import_initiated_time, False)
        activity_metadata_dict["import_dict"] = import_dict

    # Work through the parsed info; process and store any activity information
    # found (specific routines depend on file type: .gpx/.tcx and .fit have very
    # different needs).
    # File-based sources (direct upload, generic + Strava bulk import) carry no
    # provider activity id, so their stable identity for idempotency is the
    # SHA-256 of the (already-decompressed) file. Garmin syncs key off the
    # provider id instead, so skip the hash there.
    content_hash = None if from_garmin else core_file_uploads.sha256_file(file_path)
    import_source = activities_contracts.ImportSource(
        kind="garmin" if from_garmin else "bulk_import" if is_bulk_import else "upload",
        content_hash=content_hash,
    )
    created_activities = []
    created_activity: activities_schema.Activity | None = None
    ids_to_filename = ""
    if file_extension.lower() in (
        ".gpx",
        ".tcx",
    ):
        # Re-attach owner privacy defaults + gear (the parser is now pure) before
        # the Strava bulk-import metadata can override the gear.
        enrichment.enrich_parsed_activity(
            parsed_info["activity"],
            user_id=token_user_id,
            user_privacy_settings=user_privacy_settings,
            db=db,
            from_garmin=from_garmin,
            garminconnect_gear=garminconnect_gear,
            garmin_connect_activity_id=int(garmin_connect_activity_id) if garmin_connect_activity_id else None,
        )

        # Add import metadata and Strava activities.csv metadata to parsed_info
        if is_bulk_import:
            parsed_info = strava_bulk_import_utils.append_bulk_import_metadata_to_activity(
                parsed_info, activity_metadata_dict
            )

        # Store the activity in the database
        created_activity = ingestion_service.store_parsed_activity(
            file_adapter.parsed_info_to_parsed_activity(parsed_info, source=import_source), db
        )
        created_activities.append(created_activity)
        ids_to_filename += str(created_activity.id)
    elif file_extension.lower() == ".fit":
        # Persist the file's exercise-title reference rows (parsed as data — the
        # parser no longer writes them).
        exercise_titles = parsed_info.get("exercise_titles")
        if exercise_titles:
            activity_exercise_titles_crud.create_activity_exercise_titles(exercise_titles, db)

        # Split the records by activity (check for multiple activities in the file)
        split_records_by_activity = fit_utils.split_records_by_activity(parsed_info)

        # Create activity objects for each activity in the file (pure parse output)
        created_activities_objects = fit_utils.create_activity_objects(
            split_records_by_activity,
            token_user_id,
            user.timezone,
        )

        garmin_activity_id = int(garmin_connect_activity_id) if garmin_connect_activity_id else None
        for activity in created_activities_objects:
            # Re-attach owner privacy defaults, gear, and Garmin ids before the
            # Strava bulk-import metadata can override the gear (matches the old
            # parser-then-bulk ordering).
            enrichment.enrich_parsed_activity(
                activity["activity"],
                user_id=token_user_id,
                user_privacy_settings=user_privacy_settings,
                db=db,
                from_garmin=from_garmin,
                garminconnect_gear=garminconnect_gear,
                garmin_connect_activity_id=garmin_activity_id,
            )

            activity = _prepare_bulk_import_activity(
                activity,
                is_bulk_import,
                created_activities_objects,
                strava_activities,
                activity_metadata_dict,
            )
            if activity is None:
                continue

            # Store the activity in the database
            created_activity = ingestion_service.store_parsed_activity(
                file_adapter.parsed_info_to_parsed_activity(activity, source=import_source), db
            )

            created_activities.append(created_activity)

        ids_to_filename = "_".join(str(activity.id) for activity in created_activities)
    else:
        # Should no longer get here due to screening of extensions
        # in router.py, but why not.
        logger.error(f"File extension not supported: {file_extension}", extra=core_logger.context(console=True))

    # Persist the retained source file through the platform StorageProvider — the
    # same abstraction thumbnails use — so file-based ingestion works unchanged on
    # local disk or object storage instead of being pinned to this node's disk.
    # Each created activity owns its own copy keyed by id, so its lifecycle
    # (profile export, deletion) is independent, including the several activities
    # parsed from a single multi-activity .fit. The staging/temp input is consumed
    # (removed) afterwards, exactly as the previous move-into-processed did.
    activity_ids = [activity.id for activity in created_activities if activity.id is not None]
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

    # Import any associated media and log completion.
    if is_bulk_import:
        logger.info(
            f"Bulk file import: file {file_base_name} successfully processed and stored for activities {ids_to_filename}",
            extra=core_logger.context(console=True),
        )

        # Deal with Strava bulk import media.
        # Note - even multi-activity .fit files are good with this code, as there should only be a single imported activity per file in the Strava activities file directory.
        if strava_activities and created_activity is not None:
            strava_bulk_import_utils.import_media_from_strava_bulk_export(
                strava_activities,
                created_activity,
                file_base_name,
                db,
            )

        logger.info(
            f"Bulk file import: Import work complete for file {file_base_name}.",
            extra=core_logger.context(console=True),
        )

    # Return the created activities
    return created_activities


def _validate_prepare_and_store_file(
    token_user_id: int,
    file_path: str,
    db: Session,
    *,
    from_garmin: bool = False,
    is_bulk_import: bool = False,
    garminconnect_gear: dict | None = None,
    strava_activities: dict | None = None,
    import_initiated_time: str | None = None,
    users_existing_gear_nickname_to_id: dict | None = None,
    activity_name: str | None = None,
) -> list[activities_schema.Activity] | None:
    """Validate, decompress, and store one on-disk activity file — **raising** on failure.

    The shared raising core behind both the swallowing background entry
    (:func:`parse_and_store_activity_from_file`, which moves the file to the
    error dir and returns ``None``) and the durable bulk-import job body
    (:func:`store_bulk_import_file`, which lets the failure propagate so the job
    runner retries and eventually dead-letters). Does no error-directory handling
    itself — the caller owns the failure policy.

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the activity file to parse.
        db: SQLAlchemy database session.
        from_garmin: Whether the file originates from a Garmin Connect sync.
        is_bulk_import: Whether this file is part of a bulk import.
        garminconnect_gear: Garmin Connect gear metadata to associate.
        strava_activities: Strava bulk-import metadata dict keyed by filename.
        import_initiated_time: ISO timestamp of when the bulk import was initiated.
        users_existing_gear_nickname_to_id: Gear nickname → internal id mapping.
        activity_name: Optional override for the activity name.

    Returns:
        List of created activity schema objects.
    """
    # Get file extension
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

    # The Strava bulk-import metadata dict is keyed by the original
    # (pre-decompression) base filename, and the Garmin activity id is parsed
    # from it — capture both before any ``.gz`` handling rewrites the path.
    _, file_base_name = os.path.split(file_path)

    garmin_connect_activity_id = None
    if from_garmin:
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

    return _store_activities_from_file(
        token_user_id,
        file_path,
        file_extension,
        file_base_name,
        db,
        from_garmin=from_garmin,
        is_bulk_import=is_bulk_import,
        garminconnect_gear=garminconnect_gear,
        strava_activities=strava_activities,
        import_initiated_time=import_initiated_time,
        users_existing_gear_nickname_to_id=users_existing_gear_nickname_to_id,
        garmin_connect_activity_id=garmin_connect_activity_id,
        activity_name=activity_name,
    )


def store_bulk_import_file(
    user_id: int,
    file_path: str,
    import_initiated_time: str | None,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Import one bulk-import file, **raising** on failure (the durable job body).

    The per-file body of the durable bulk-import job: it validates, decompresses,
    and stores the file exactly like the background entry but does **not** swallow
    errors or move the file — a failure propagates so the durable-job runner
    retries with backoff and eventually dead-letters. The durable subscriber owns
    moving a dead-lettered file to the import-error directory.

    Args:
        user_id: ID of the user performing the import.
        file_path: Absolute path to the activity file to parse.
        import_initiated_time: ISO timestamp of when the bulk import was initiated.
        db: SQLAlchemy database session.

    Returns:
        List of created activity schema objects.
    """
    return _validate_prepare_and_store_file(
        user_id,
        file_path,
        db,
        is_bulk_import=True,
        import_initiated_time=import_initiated_time,
    )


def parse_and_store_activity_from_file(
    token_user_id: int,
    file_path: str,
    db: Session,
    from_garmin: bool = False,
    is_bulk_import: bool = False,
    garminconnect_gear: dict | None = None,
    strava_activities: dict | None = None,
    import_initiated_time: str | None = None,
    users_existing_gear_nickname_to_id: dict | None = None,
    activity_name: str | None = None,
) -> list[activities_schema.Activity] | None:
    """Validate an on-disk activity file and persist it (bulk/Garmin/Strava entry).

    Thin entry point for background ingestion (Garmin sync, Strava/generic bulk
    import). Validates and (if needed) decompresses the file, then delegates to
    the shared ``_store_activities_from_file`` core. Unlike the upload entry it
    never raises to its caller: on failure it (for bulk imports) moves the
    offending file to the import-error directory and returns ``None`` so the
    batch can continue.

    Supports .gpx, .tcx, .fit, and .gz files. Must be called from a worker thread
    with no running event loop (Starlette threadpool, the bulk ThreadPoolExecutor,
    or ``asyncio.to_thread``) because file validation runs a private event loop
    internally.

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the activity file to parse.
        db: SQLAlchemy database session.
        from_garmin: Whether the file originates from a Garmin Connect sync.
        garminconnect_gear: Garmin Connect gear metadata to associate with the
            activity.
        strava_activities: Strava bulk-import metadata dict keyed by filename,
            then by activities.csv column header.
        import_initiated_time: ISO timestamp of when the bulk import was
            initiated.
        users_existing_gear_nickname_to_id: Mapping of gear nickname to internal
            gear ID, used during Strava bulk imports.
        activity_name: Optional override for the activity name.

    Returns:
        List of created activity schema objects, or None if the file could not be
        parsed or persisted.
    """
    try:
        return _validate_prepare_and_store_file(
            token_user_id,
            file_path,
            db,
            from_garmin=from_garmin,
            is_bulk_import=is_bulk_import,
            garminconnect_gear=garminconnect_gear,
            strava_activities=strava_activities,
            import_initiated_time=import_initiated_time,
            users_existing_gear_nickname_to_id=users_existing_gear_nickname_to_id,
            activity_name=activity_name,
        )
    except (
        HTTPException,
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        if is_bulk_import:
            # Log the exception
            logger.error(
                f"Bulk file import: Error while parsing {file_path} in parse_and_store_activity_from_file - {err!s}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            try:
                # Move the exception-causing file to an import errors directory.
                if strava_activities:
                    # Use Strava bulk import errors directory if we are doing a Strava bulk import
                    error_file_dir = core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR
                else:
                    # otherwise use standard bulk import error directory
                    error_file_dir = core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR
                os.makedirs(error_file_dir, exist_ok=True)
                core_file_uploads.move_within(file_path, error_file_dir, filename=os.path.basename(file_path))
                logger.error(
                    f"Bulk file import: Due to import error, file {file_path} has been moved to {error_file_dir}",
                    extra=core_logger.context(console=True),
                )
            except OSError:
                logger.error(
                    f"Bulk file import: Failed to move the error-producing file {file_path} to the import-error directory.",
                    extra=core_logger.context(console=True),
                )
        logger.error(
            f"Error in parse_and_store_activity_from_file - {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        # Background-task callers expect ``None`` on failure rather
        # than re-raising; make that contract explicit.
        return None


def parse_and_store_activity_from_uploaded_file(
    token_user_id: int,
    file: UploadFile,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Persist an uploaded activity file and return the result.

    Thin entry point for the synchronous upload route. Validates the filename and
    extension, streams the upload to disk, decompresses ``.gz`` payloads, then
    delegates to the shared ``_store_activities_from_file`` core. On failure it
    removes any partial upload artifacts and raises ``HTTPException`` (the upload
    route's contract), rather than swallowing the error like the bulk entry.

    Args:
        token_user_id: Authenticated user ID.
        file: Incoming FastAPI UploadFile.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        HTTPException: 400/404/406/413 on validation errors,
            500 on internal failures.
    """
    # Validate filename exists
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Pre-check the extension so we can short-circuit with a
    # human-friendly 406 before invoking the validator (which would
    # otherwise raise a generic ExtensionSecurityError -> 400).
    _, file_extension = os.path.splitext(file.filename)
    if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=("File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"),
        )

    upload_dir = core_config.settings.FILES_DIR
    upload_kind = (
        core_file_uploads.UploadKind.GZIP if file_extension.lower() == ".gz" else core_file_uploads.UploadKind.ACTIVITY
    )
    # Server-generated filename to defeat path traversal and
    # collisions; the upload is renamed to ``{ids}{ext}`` after a
    # successful parse via ``move_within`` below.
    storage_name = f"{uuid.uuid4().hex}{file_extension.lower()}"
    upload_artifacts: list[str] = []

    try:
        # Validate (signature/size/MIME via safeuploads) and stream
        # the upload to disk in one unified step. The streaming
        # writer enforces the activity/gzip byte cap and writes via
        # a ``.part``-then-rename for atomicity.
        file_path = core_file_uploads.save_validated_upload_sync(
            file,
            kind=upload_kind,
            upload_dir=upload_dir,
            filename=storage_name,
        )
        upload_artifacts.append(file_path)

        if file_extension.lower() == ".gz":
            file_path, file_extension = core_file_uploads.decompress_gzip(file_path)
            # ``decompress_gzip`` consumes (removes) the staging .gz and
            # returns the decompressed temp file; track it so a later failure
            # cleans it up.
            upload_artifacts.append(file_path)
            # Re-validate after decompression so the inner payload
            # still matches one of the supported activity formats.
            if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS or file_extension.lower() == ".gz":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=("Decompressed file extension is not supported"),
                )
            # Defense in depth: signature-check the inner payload
            # via the same safeuploads validator used for direct
            # activity uploads.
            core_file_uploads.validate_local_file_sync(
                file_path,
                kind=core_file_uploads.UploadKind.ACTIVITY,
            )

        _, file_base_name = os.path.split(file_path)

        # Delegate to the shared ingestion core. The upload route is synchronous,
        # so Starlette already runs it on a threadpool worker.
        created_activities = _store_activities_from_file(
            token_user_id,
            file_path,
            file_extension,
            file_base_name,
            db,
        )
        if created_activities is None:
            core_file_uploads.remove_files(upload_artifacts)
        return created_activities
    except HTTPException:
        core_file_uploads.remove_files(upload_artifacts)
        raise
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        # Log the exception
        logger.error(f"Error in parse_and_store_activity_from_uploaded_file - {err!s}", exc_info=err)
        core_file_uploads.remove_files(upload_artifacts)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def process_all_files_sync(
    user_id: int,
    file_paths: list[str],
    import_initiated_time: str,
):
    """
    Process all files sequentially in single thread.

    Args:
        user_id: User ID.
        file_paths: List of file paths to process.
    """
    db = next(core_database.get_db())
    try:
        total_files = len(file_paths)
        for idx, file_path in enumerate(file_paths, 1):
            logger.info(
                f"Processing file {idx}/{total_files}: {Path(file_path).name}", extra=core_logger.context(console=True)
            )
            parse_and_store_activity_from_file(
                user_id,
                file_path,
                db,
                is_bulk_import=True,
                import_initiated_time=import_initiated_time,
            )

        logger.info(
            f"Bulk import completed: {total_files} files processed for user {user_id}",
            extra=core_logger.context(console=True),
        )
    finally:
        db.close()
