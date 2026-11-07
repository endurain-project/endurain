"""Domain event channel names owned by the profile import."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published once per accepted profile import. A durable subscriber runs it on a worker when
# durable jobs are enabled; otherwise a bus subscriber runs it on the in-process pool.
USERS_PROFILE_IMPORT_REQUESTED = "users.profile_import_requested"

# Published once per accepted profile export; consumed like the import above.
USERS_PROFILE_EXPORT_REQUESTED = "users.profile_export_requested"


class ProfileImportRequestedPayload(VersionedPayload):
    """Validated payload for the ``users.profile_import_requested`` event.

    Attributes:
        user_id: The user whose profile the archive is imported into.
        staged_key: Storage key of the staged archive; it must sit under the user's own prefix.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    staged_key: str


class ProfileExportRequestedPayload(VersionedPayload):
    """Validated payload for the ``users.profile_export_requested`` event.

    Attributes:
        user_id: The user whose profile is exported.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
