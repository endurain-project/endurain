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
import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_file_import.utils_fit as fit_utils
import modules.activities.activity_file_import.utils_gpx as gpx_utils
import modules.activities.activity_file_import.utils_tcx as tcx_utils
import modules.activities.activity_ingestion.enrichment as enrichment
import modules.activities.activity_ingestion.file_adapter as file_adapter
import modules.strava.bulk_import_utils as strava_bulk_import_utils
import modules.users.users.crud as users_crud
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud

# Maximum size accepted when decompressing a gzipped activity
# upload. Mirrors core_file_uploads' activity cap; safeuploads
# enforces the same limit on the wrapping ``.gz`` upload before we
# get here, but we re-cap defensively while expanding the inner
# payload (decompression-bomb defense in depth).
_MAX_DECOMPRESSED_ACTIVITY_BYTES = 200 * 1024 * 1024
# Chunk size used while streaming decompressed bytes to disk.
_DECOMPRESS_CHUNK_BYTES = 1024 * 1024


def _sha256_file(file_path: str) -> str:
    """Return the hex SHA-256 of a file's contents (streamed in chunks).

    Gives provider-less file imports (upload / bulk import) a stable idempotency
    fingerprint: re-importing the exact same file yields the same hash, so
    :func:`ingestion_service.store_parsed_activity` can no-op it. The file is
    hashed after ``.gz`` decompression, so a ``.gpx`` and its ``.gpx.gz`` produce
    the same key.
    """
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_DECOMPRESS_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def handle_gzipped_file(
    file_path: str,
) -> tuple[str, str]:
    """Handle gzipped files with bounded extraction.

    Args:
        file_path: Path to the gzipped activity file.

    Returns:
        Tuple containing the temporary file path and inner
        extension.

    Raises:
        HTTPException: 400 for invalid gzip content or 413 when
            decompressed content exceeds the configured limit.
    """
    path = Path(file_path)

    inner_filename = path.stem  # eg "activity_1234567890.fit"
    inner_file_extension = Path(inner_filename).suffix  # eg ".gz"
    temp_file_path: str | None = None
    bytes_written = 0

    try:
        with (
            gzip.open(path, "rb") as gzipped_file,
            NamedTemporaryFile(
                suffix=inner_file_extension,
                delete=False,
            ) as temp_file,
        ):
            temp_file_path = temp_file.name
            while True:
                chunk = gzipped_file.read(_DECOMPRESS_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_DECOMPRESSED_ACTIVITY_BYTES:
                    temp_file.close()
                    with contextlib.suppress(OSError):
                        os.remove(temp_file_path)
                    raise HTTPException(
                        status_code=(status.HTTP_413_CONTENT_TOO_LARGE),
                        detail=("Decompressed file exceeds maximum allowed size"),
                    )
                temp_file.write(chunk)
            temp_file.flush()

        core_logger.print_to_log_and_console(
            f"Decompressed {path} with inner type {inner_file_extension} to {temp_file_path}"
        )

        core_file_uploads.move_within(str(path), core_config.FILES_PROCESSED_DIR, filename=path.name)

        return temp_file_path, inner_file_extension
    except HTTPException:
        raise
    except (OSError, EOFError, gzip.BadGzipFile) as err:
        if temp_file_path is not None:
            with contextlib.suppress(OSError):
                os.remove(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid gzip file",
        ) from err


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
        core_logger.print_to_log_and_console(
            "Bulk activity import of multi-activity .fit file: "
            "skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file "
            "in the Strava activities.csv file.",
            "debug",
        )
        return None

    # Add import metadata and Strava activities.csv metadata
    activity = strava_bulk_import_utils.append_bulk_import_metadata_to_activity(activity, activity_metadata_dict)
    return activity


def _cleanup_upload_artifacts(file_paths: list[str]) -> None:
    """Remove files created during failed activity uploads.

    Args:
        file_paths: Files to remove if they still exist.

    Returns:
        None.

    Raises:
        None.
    """
    for file_path in file_paths:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except OSError as err:
            core_logger.print_to_log(
                f"Failed to cleanup upload artifact {file_path}: {err}",
                "warning",
                exc=err,
            )


def parse_file(
    token_user_id: int,
    file_extension: str,
    filename: str,
    activity_name: str | None = None,
) -> dict | None:
    try:
        if filename.lower() != "bulk_import/__init__.py":
            core_logger.print_to_log(f"Parsing file: {filename}")
            parsed_info: dict[str, Any]
            # Choose the appropriate parser based on file extension. The parsers
            # are pure (no db / privacy / gear / provider coupling — plan §18.2 /
            # A7); the orchestrator re-attaches that domain context afterwards.
            if file_extension.lower() == ".gpx":
                # Parse the GPX file. parse_gpx_file returns a ParsedGpxData
                # TypedDict; normalize it to a plain dict so ``parsed_info`` is a
                # single dict type across the gpx/tcx/fit branches downstream.
                parsed_info = dict(
                    gpx_utils.parse_gpx_file(
                        filename,
                        token_user_id,
                        activity_name,
                    )
                )
            elif file_extension.lower() == ".tcx":
                parsed_info = tcx_utils.parse_tcx_file(
                    filename,
                    token_user_id,
                    activity_name,
                )
            elif file_extension.lower() == ".fit":
                # Parse the FIT file
                parsed_info = fit_utils.parse_fit_file(filename, activity_name)
            else:
                # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail="File extension not supported. Supported file extensions are .gpx, .fit and .tcx",
                )
            return parsed_info
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
        core_logger.print_to_log(f"Error in parse_file - {err}", "error", exc=err)
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
    content_hash = None if from_garmin else _sha256_file(file_path)
    import_source = activities_schema.ImportSource(
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
        # parser no longer writes them; plan §18.2 / A7).
        exercise_titles = parsed_info.get("exercise_titles")
        if exercise_titles:
            activity_exercise_titles_crud.create_activity_exercise_titles(exercise_titles, db)

        # Split the records by activity (check for multiple activities in the file)
        split_records_by_activity = fit_utils.split_records_by_activity(parsed_info)

        # Create activity objects for each activity in the file (pure parse output)
        created_activities_objects = fit_utils.create_activity_objects(
            split_records_by_activity,
            token_user_id,
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
        core_logger.print_to_log_and_console(f"File extension not supported: {file_extension}", "error")

    # Define the directory where the processed files will be stored
    processed_dir = core_config.FILES_PROCESSED_DIR

    # Define new file path with activity ID as filename
    new_file_name = f"{ids_to_filename}{file_extension}"

    # Move the file to the processed directory
    core_file_uploads.move_within(file_path, processed_dir, filename=new_file_name)

    # Log file move, import any associated media, and log completion.
    if is_bulk_import:
        core_logger.print_to_log_and_console(
            f"Bulk file import: File successfully processed and moved. {file_path} - has become {new_file_name}"
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

        core_logger.print_to_log_and_console(f"Bulk file import: Import work complete for file {file_base_name}.")

    # Return the created activities
    return created_activities


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
            kind=(
                core_file_uploads.UploadKind.GZIP if file_extension == ".gz" else core_file_uploads.UploadKind.ACTIVITY
            ),
        )

        # The Strava bulk-import metadata dict is keyed by the original
        # (pre-decompression) base filename, and the Garmin activity id is parsed
        # from it — capture both before any ``.gz`` handling rewrites the path.
        _, file_base_name = os.path.split(file_path)

        garmin_connect_activity_id = None
        if from_garmin:
            garmin_connect_activity_id = os.path.basename(file_path).split("_")[0]

        if file_extension == ".gz":
            file_path, file_extension = handle_gzipped_file(file_path)
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
            core_logger.print_to_log_and_console(
                f"Bulk file import: Error while parsing {file_path} in parse_and_store_activity_from_file - {err!s}",
                "error",
                exc=err,
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
                core_logger.print_to_log_and_console(
                    f"Bulk file import: Due to import error, file {file_path} has been moved to {error_file_dir}",
                    "error",
                )
            except OSError:
                core_logger.print_to_log_and_console(
                    f"Bulk file import: Failed to move the error-producing file {file_path} to the import-error directory.",
                    "error",
                )
        core_logger.print_to_log_and_console(
            f"Error in parse_and_store_activity_from_file - {err}",
            "error",
            exc=err,
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
            original_file_path = file_path
            file_path, file_extension = handle_gzipped_file(file_path)
            upload_artifacts.append(file_path)
            upload_artifacts.append(
                os.path.join(
                    core_config.FILES_PROCESSED_DIR,
                    os.path.basename(original_file_path),
                )
            )
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
            _cleanup_upload_artifacts(upload_artifacts)
        return created_activities
    except HTTPException:
        _cleanup_upload_artifacts(upload_artifacts)
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
        core_logger.print_to_log(
            f"Error in parse_and_store_activity_from_uploaded_file - {err!s}",
            "error",
            exc=err,
        )
        _cleanup_upload_artifacts(upload_artifacts)
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
            core_logger.print_to_log_and_console(f"Processing file {idx}/{total_files}: {file_path}")
            parse_and_store_activity_from_file(
                user_id,
                file_path,
                db,
                is_bulk_import=True,
                import_initiated_time=import_initiated_time,
            )
            # Small delay between files
            time.sleep(0.1)

        core_logger.print_to_log_and_console(f"Bulk import completed: {total_files} files processed for user {user_id}")
    finally:
        db.close()
