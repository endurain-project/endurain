"""Typed callbacks the users namespace asks composition to install.

Deleting an account must erase the data other modules keep about the user, and creating or editing one
must stage the data other modules keep per user. Those modules sit above users (activities consumes the
users surface), so users states what it needs and ``app/module_registry.py`` installs the answers.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

#: ``(user_id, limit, db)`` -> stages the deletion of up to ``limit`` activities the user owns and returns
#: how many it touched; the caller commits and repeats until it returns 0. Going through the owning module
#: is what lets it clean up the blobs stored per activity.
ActivitiesEraser = Callable[[int, int, Session], int]

#: ``(user_id, storage)`` -> removes files other modules stored for the user. Housekeeping that
#: runs after the deletion is committed, so it logs a failure instead of raising.
StagedFilesEraser = Callable[[int, platform_providers.StorageProvider], None]

#: ``(user_id, db)`` -> stages the per-user rows other modules keep for a newly created user and returns what
#: it staged; never commits, so the rows land in the creating transaction.
NewUserStager = Callable[[int, Session], object]

#: ``(user_id, height_cm, db)`` -> stages the recalculation of what other modules derive from the user's
#: height (``None`` when unknown); never commits.
HeightChangeStager = Callable[[int, float | None, Session], None]


class FollowCounts(Protocol):
    """Accepted follower and following counts visible to a profile viewer."""

    @property
    def followers(self) -> int:
        """Number of accepted followers."""
        ...

    @property
    def following(self) -> int:
        """Number of accepted followees."""
        ...


#: ``(target_user_id, requester_user_id, db)`` -> the target's accepted network counts, or ``None`` when the
#: network is private to the requester.
FollowCountsReader = Callable[[int, int, Session], FollowCounts | None]


@dataclass(frozen=True, kw_only=True)
class UserErasers:
    """The erasures composition installs for the users namespace.

    Attributes:
        delete_activities: Stages the deletion of a batch of a user's activities and their stored files.
        delete_staged_files: Removes the archives staged for the user's profile export and imports.
        delete_bulk_import_errors: Removes the failed bulk-import files kept for the user.
    """

    delete_activities: ActivitiesEraser
    delete_staged_files: StagedFilesEraser
    delete_bulk_import_errors: StagedFilesEraser


@dataclass(frozen=True, kw_only=True)
class UserLifecycleHooks:
    """The staging composition installs for a user's creation and edits.

    Attributes:
        stage_new_user: Stages the per-user rows other modules keep for a new user.
        stage_height_change: Stages the recalculation of values derived from the user's height.
    """

    stage_new_user: NewUserStager
    stage_height_change: HeightChangeStager


@dataclass(frozen=True, kw_only=True)
class ProfileReaders:
    """The reads composition installs for the profile overview.

    Attributes:
        follow_counts: Reads the profile owner's accepted follower and following counts.
    """

    follow_counts: FollowCountsReader
