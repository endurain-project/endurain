"""Pydantic response shapes for the profile import and export."""

from pydantic import BaseModel, ConfigDict, Field

import modules.activities.activity.schema as activity_schema
import modules.users.users.schema as users_schema
import modules.users.users_profile.constants as profile_constants


class UserProfileOverviewRead(BaseModel):
    """Public profile and summary metrics displayed on a user's profile page.

    Attributes:
        user: The profile's public user projection.
        week_stats: Visible per-sport activity totals for the current week.
        month_stats: Visible per-sport activity totals for the current month.
        month_activity_count: Visible activity count for the current month.
        followers_count: Accepted followers, or None when the viewer cannot see the network.
        following_count: Accepted followees, or None when the viewer cannot see the network.
    """

    user: users_schema.UserPublicRead
    week_stats: activity_schema.ActivityStatsRead
    month_stats: activity_schema.ActivityStatsRead
    month_activity_count: int = Field(..., ge=0)
    followers_count: int | None = Field(default=None, ge=0)
    following_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ProfileImportStatus(BaseModel):
    """Where the authenticated user's profile import is.

    Attributes:
        status: Lifecycle state of the import.
        failure: Why the import failed; set only when it failed.
        imported: How many items of each kind were imported; set only when it completed.
    """

    status: profile_constants.ImportStatus = Field(..., description="Lifecycle state of the import")
    failure: profile_constants.ImportFailure | None = Field(default=None, description="Reason the import failed")
    imported: dict[str, int] | None = Field(default=None, description="Items imported per kind, once completed")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ProfileExportStatus(BaseModel):
    """Where the authenticated user's profile export is.

    Attributes:
        status: Lifecycle state of the export.
        failure: Why the export failed; set only when it failed.
        size_bytes: Size of the archive; set only when it completed and can be downloaded.
    """

    status: profile_constants.ExportStatus = Field(..., description="Lifecycle state of the export")
    failure: profile_constants.ExportFailure | None = Field(default=None, description="Reason the export failed")
    size_bytes: int | None = Field(default=None, description="Archive size in bytes, once completed")

    model_config = ConfigDict(from_attributes=True, extra="forbid")
