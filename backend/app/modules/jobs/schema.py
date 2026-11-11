"""Pydantic schemas for the job routes."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field

import core.pagination as core_pagination
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.garmin.schema as garmin_schema
import modules.strava.schema as strava_schema
import modules.users.users.schema as users_schema
import modules.users.users_profile.schema as users_profile_schema


class JobKind(StrEnum):
    """What a background job does; the ``kind`` of every model in :data:`JobRead`.

    Attributes:
        ACTIVITY_UPLOAD: An uploaded activity file being imported.
        ACTIVITY_REFRESH: A pull of new activities from the linked providers.
        ACTIVITY_BULK_IMPORT: One dropped bulk-import archive being imported.
        ACTIVITIES_BULK_EDIT: A change to the visibility of all the user's activities.
        GARMIN_LINK: A Garmin Connect login, which may wait for an MFA code.
        GARMIN_SYNC_GEAR: A pull of gear from Garmin Connect.
        GARMIN_SYNC_HEALTH: A pull of health data from Garmin Connect.
        STRAVA_LINK: A Strava account link.
        STRAVA_GEAR: A pull of gear from Strava.
        STRAVA_UNLINK: A Strava account unlink.
        USER_DELETION: An account deletion an administrator queued.
        PROFILE_EXPORT: A profile export archive being built.
        PROFILE_IMPORT: A profile export archive being imported.
    """

    ACTIVITY_UPLOAD = "activity_upload"
    ACTIVITY_REFRESH = "activity_refresh"
    ACTIVITY_BULK_IMPORT = "activity_bulk_import"
    ACTIVITIES_BULK_EDIT = "activities_bulk_edit"
    GARMIN_LINK = "garmin_link"
    GARMIN_SYNC_GEAR = "garmin_sync_gear"
    GARMIN_SYNC_HEALTH = "garmin_sync_health"
    STRAVA_LINK = "strava_link"
    STRAVA_GEAR = "strava_gear"
    STRAVA_UNLINK = "strava_unlink"
    USER_DELETION = "user_deletion"
    PROFILE_EXPORT = "profile_export"
    PROFILE_IMPORT = "profile_import"


#: A job's status, told apart by ``kind``; each kind adds its own fields to the shared envelope.
JobRead = Annotated[
    activity_ingestion_schema.ActivityIngestionJobRead
    | activity_schema.ActivitiesBulkEditStatus
    | garmin_schema.GarminLinkStatus
    | garmin_schema.GarminSyncStatus
    | strava_schema.StravaSyncStatus
    | users_schema.UserDeletionStatus
    | users_profile_schema.ProfileExportStatus
    | users_profile_schema.ProfileImportStatus,
    Field(discriminator="kind"),
]


class JobPage(core_pagination.CursorPage[JobRead]):
    """A keyset slice of the caller's jobs, newest first."""
