"""Domain event channels owned by the account-security package.

Payloads carry ids and the kind of change only: events are persisted, so no secret may be put in one.
"""

from enum import StrEnum
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a change to how a user proves who they are (a credential, a second factor, an API key or a
# sign-in provider link), after the account or its MFA sign-in is locked by repeated failed sign-ins, and after an
# administrator changed the account's role or deactivated it or its deletion was requested.
ACCOUNT_SECURITY_CHANGED = "auth.account_security_changed"


class AccountSecurityChange(StrEnum):
    """The kind of change an ``auth.account_security_changed`` event reports."""

    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    PASSWORD_SET_BY_ADMIN = "password_set_by_admin"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_RESET_BY_ADMIN = "mfa_reset_by_admin"
    PASSWORD_CHANGE_REQUIRED_BY_ADMIN = "password_change_required_by_admin"
    BACKUP_CODES_GENERATED = "backup_codes_generated"
    API_KEY_CREATED = "api_key_created"
    IDENTITY_PROVIDER_UNLINKED = "identity_provider_unlinked"
    ACCOUNT_LOCKED = "account_locked"
    MFA_LOCKED = "mfa_locked"
    BACKUP_CODE_USED = "backup_code_used"
    REFRESH_TOKEN_REUSE_DETECTED = "refresh_token_reuse_detected"
    ROLE_CHANGED_BY_ADMIN = "role_changed_by_admin"
    ACCOUNT_DEACTIVATED_BY_ADMIN = "account_deactivated_by_admin"
    ACCOUNT_DELETION_REQUESTED = "account_deletion_requested"


class AccountSecurityChangedPayload(VersionedPayload):
    """Validated payload for the ``auth.account_security_changed`` event.

    Attributes:
        user_id: The user whose account security changed.
        change: What changed.
        idp_id: The identity provider concerned, for an unlink.
        access_type: The access type the user now has, for a role change.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    change: AccountSecurityChange
    idp_id: int | None = None
    access_type: str | None = None
