"""Domain event channels owned by the account-security package.

Payloads carry ids and the kind of change only: events are persisted, so no secret may be put in one.
"""

from enum import StrEnum
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a change to how a user proves who they are: a credential, a second factor, an API key or a
# sign-in provider link.
ACCOUNT_SECURITY_CHANGED = "auth.account_security_changed"


class AccountSecurityChange(StrEnum):
    """The kind of change an ``auth.account_security_changed`` event reports."""

    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    PASSWORD_SET_BY_ADMIN = "password_set_by_admin"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    BACKUP_CODES_GENERATED = "backup_codes_generated"
    API_KEY_CREATED = "api_key_created"
    IDENTITY_PROVIDER_UNLINKED = "identity_provider_unlinked"


class AccountSecurityChangedPayload(VersionedPayload):
    """Validated payload for the ``auth.account_security_changed`` event.

    Attributes:
        user_id: The user whose account security changed.
        change: What changed.
        idp_id: The identity provider concerned, for an unlink.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    change: AccountSecurityChange
    idp_id: int | None = None
