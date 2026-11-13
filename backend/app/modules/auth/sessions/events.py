"""Domain event channels owned by sessions.

Payloads are persisted with the event log, so they hold the ids a subscriber needs to find a session and nothing
else: never a token or a hash.
"""

import uuid
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after sessions were revoked (logout, a revocation by the user or an administrator, a password change or
# reset, a deactivated or deleted account, a detected refresh-token reuse), so whatever was opened with them can end.
SESSIONS_REVOKED = "auth.sessions_revoked"


class SessionsRevokedPayload(VersionedPayload):
    """Validated payload for the ``auth.sessions_revoked`` event.

    Attributes:
        user_id: The user whose sessions were revoked.
        session_id: The one revoked session, or None when every session of the user was revoked.
        except_session_id: With no ``session_id``, the one session of the user that was kept.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID
    session_id: str | None = None
    except_session_id: str | None = None
