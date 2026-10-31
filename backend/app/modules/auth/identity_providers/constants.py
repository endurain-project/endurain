"""Identity-provider constants."""

from enum import StrEnum

#: Icon keys that ship with a bundled logo; the only values the ``icon`` field accepts. Any other logo is uploaded.
BUILTIN_ICONS = frozenset({"authelia", "authentik", "casdoor", "keycloak", "pocketid"})

#: Storage area of the uploaded provider icons, keyed by identity-provider id.
ICON_STORAGE_AREA = "identity_provider_icons"

#: Largest accepted icon upload, in bytes. A provider logo is a small image shown to every visitor of the login page.
ICON_MAX_BYTES = 1024 * 1024

#: How long one refresh of an identity-provider token may hold its claim: longer than the provider calls it
#: makes, so a live refresh keeps it, and short enough that a lost worker blocks the next one only briefly.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60

#: How recent the identity-provider sign-in of a step-up must be. Sent as ``max_age`` and enforced on the ID
#: token's ``auth_time``. Not 0: some providers read ``max_age=0`` as unset, and the margin absorbs whole-second
#: ``auth_time`` values and clock skew.
STEP_UP_MAX_AGE_SECONDS = 60

#: How long a step-up ticket stays redeemable after the provider's callback: long enough to finish what the
#: step-up was for (scanning an MFA enrolment code, typing a new email address), and still one request only,
#: in the session and browser that started it.
STEP_UP_TICKET_TTL_SECONDS = 300


class StepUpAction(StrEnum):
    """A sensitive operation a step-up re-authentication can authorise, so a ticket for one cannot pay for another.

    Attributes:
        API_KEY_CREATE: Create an API key.
        IDP_LINK: Mint a token that links an identity provider.
        IDP_UNLINK: Unlink an identity provider.
        EMAIL_CHANGE: Change the account's email address.
        ACCOUNT_DELETE: Delete the account.
        MFA_ENABLE: Enable MFA.
        MFA_DISABLE: Disable MFA.
        MFA_BACKUP_CODES: Regenerate MFA backup codes.
    """

    API_KEY_CREATE = "api_key_create"
    IDP_LINK = "idp_link"
    IDP_UNLINK = "idp_unlink"
    EMAIL_CHANGE = "email_change"
    ACCOUNT_DELETE = "account_delete"
    MFA_ENABLE = "mfa_enable"
    MFA_DISABLE = "mfa_disable"
    MFA_BACKUP_CODES = "mfa_backup_codes"
