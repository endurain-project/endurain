"""Audit actions written by the identity-providers package.

Ids are stable forever: rows outlive the code. ``details`` carry ids only, never a provider token or subject.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

import modules.auth.identity_providers.constants as identity_providers_constants


class IdentityLinkRefusal(StrEnum):
    """Why a sign-in provider was not linked to an account.

    Attributes:
        PROVIDER_EMAIL_UNVERIFIED: The provider did not assert the email as verified.
        ACCOUNT_EMAIL_UNVERIFIED: The account's own email is not verified.
        LINKED_TO_ANOTHER_ACCOUNT: The provider identity is already linked to a different account.
        LINK_BY_EMAIL_DISABLED: The provider does not link a sign-in to the account that has its email.
        INVALID_STATE: The link's OAuth state was unknown, bound to another provider or already used.
        BROWSER_MISMATCH: The callback came from a browser other than the one that started the link.
        PROVIDER_ERROR: The provider answered with an error instead of a code.
        TOKEN_EXCHANGE_FAILED: The provider's token endpoint refused or failed the code exchange.
        NO_SUBJECT: The provider's claims named no subject.
        USER_NOT_FOUND: The account the link was started for no longer exists.
        ALREADY_LINKED_TO_THIS_ACCOUNT: The provider identity is already linked to this same account.
        USER_INACTIVE: The account the link was started for is no longer active.
        SESSION_ENDED: The session that started the link has ended.
        SECURITY_CHANGED: A security change of the account came after the link started.
    """

    PROVIDER_EMAIL_UNVERIFIED = "provider_email_unverified"
    ACCOUNT_EMAIL_UNVERIFIED = "account_email_unverified"
    LINKED_TO_ANOTHER_ACCOUNT = "linked_to_another_account"
    LINK_BY_EMAIL_DISABLED = "link_by_email_disabled"
    INVALID_STATE = "invalid_state"
    BROWSER_MISMATCH = "browser_mismatch"
    PROVIDER_ERROR = "provider_error"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    NO_SUBJECT = "no_subject"
    USER_NOT_FOUND = "user_not_found"
    ALREADY_LINKED_TO_THIS_ACCOUNT = "already_linked_to_this_account"
    USER_INACTIVE = "user_inactive"
    SESSION_ENDED = "session_ended"
    SECURITY_CHANGED = "security_changed"


class BackchannelLogoutRefusal(StrEnum):
    """Why a back-channel logout request from a sign-in provider was refused.

    Attributes:
        INVALID_TOKEN: The logout token did not verify or is not a logout token.
        REPLAYED: The logout token was already used.
        SIGNING_KEYS_UNAVAILABLE: The provider's issuer or signing keys could not be read, so the token could not
            be verified.
    """

    INVALID_TOKEN = "invalid_token"
    REPLAYED = "replayed"
    SIGNING_KEYS_UNAVAILABLE = "signing_keys_unavailable"


class BackchannelLogoutRefusalDetails(VersionedPayload):
    """Details of ``auth.backchannel_logout.refuse``.

    Attributes:
        idp_id: The provider the request named.
        reason: Why it was refused.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    idp_id: int
    reason: BackchannelLogoutRefusal


class IdentityProviderDetails(VersionedPayload):
    """Details of ``auth.identity_provider.create`` and ``auth.identity_provider.delete``.

    Attributes:
        provider_type: The protocol the provider speaks.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    provider_type: identity_providers_constants.ProviderType


class IdentityProviderUpdateDetails(VersionedPayload):
    """Details of ``auth.identity_provider.update``.

    Attributes:
        changed_fields: The names of the fields whose value changed; a credential is named, never shown.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


class IdentityLinkDetails(VersionedPayload):
    """Details of ``auth.identity_link.link``.

    Attributes:
        idp_id: The identity provider that was, or was to be, linked.
        reason: Why the link was refused; ``None`` when it succeeded.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 3

    idp_id: int
    reason: IdentityLinkRefusal | None = None


IDENTITY_LINK_LINK = jasil_audit.AuditAction(
    id="auth.identity_link.link",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_link.link",
    description_default="A sign-in provider was linked to an account",
    details_model=IdentityLinkDetails,
)

BACKCHANNEL_LOGOUT_REFUSE = jasil_audit.AuditAction(
    id="auth.backchannel_logout.refuse",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.backchannel_logout.refuse",
    description_default="A sign-in provider's back-channel logout request was refused",
    details_model=BackchannelLogoutRefusalDetails,
)

IDENTITY_PROVIDER_CREATE = jasil_audit.AuditAction(
    id="auth.identity_provider.create",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_provider.create",
    description_default="A sign-in provider was created",
    details_model=IdentityProviderDetails,
)

IDENTITY_PROVIDER_UPDATE = jasil_audit.AuditAction(
    id="auth.identity_provider.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_provider.update",
    description_default="A sign-in provider was changed",
    details_model=IdentityProviderUpdateDetails,
)

IDENTITY_PROVIDER_DELETE = jasil_audit.AuditAction(
    id="auth.identity_provider.delete",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_provider.delete",
    description_default="A sign-in provider was deleted",
    details_model=IdentityProviderDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    BACKCHANNEL_LOGOUT_REFUSE,
    IDENTITY_LINK_LINK,
    IDENTITY_PROVIDER_CREATE,
    IDENTITY_PROVIDER_UPDATE,
    IDENTITY_PROVIDER_DELETE,
)
